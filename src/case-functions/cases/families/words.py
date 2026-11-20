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
from ..proposals import WORD, label, shown as value

# What a plan of a change of a gateway's scale units, and its re-check right before it acts, ask of the connection count: it is read for the last CONNECTION_DAYS closed days, it has to hold a
# value for at least CONNECTION_MIN_DAYS of them (a count that was not recorded is not a count of nothing), and the most at one time in them has to be 0.
CONNECTION_DAYS = 7
CONNECTION_MIN_DAYS = 5
MAX_SCALE_UNITS = 200  # Learn, "User VPN (point-to-site) concepts": the scale units of a gateway range from 1 to 200 (capacity.py has the table; this module imports nothing of the package but the records)
# What a plan of a delete says that its re-check looks at: the words are those of the two families that were first, and a test holds them.
RE_CHECK = ("the resource is still unattached or unassigned, still carries the tag that marks it as planted by Meternaut, is still in this resource group "
            "and has no management lock")
SIZE_NAME = re.compile(r"[A-Za-z]{1,10}_[A-Za-z0-9_]{1,40}")
RESOURCE_TYPE = re.compile(r"microsoft\.[a-z0-9]{2,30}/[a-z0-9]{2,40}")
# The key path of a setting that `change-setting` changes (dotted words, the platform's own spelling, no list), and the name of a measurement that its plan cites (cases/investigate.py METRIC_NAME).
SETTING_PATH = re.compile(r"[A-Za-z][A-Za-z0-9]{0,59}(?:\.[A-Za-z][A-Za-z0-9]{0,59}){0,5}")
METRIC_WORDS = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/%()-]{0,98}")
API_VERSION = re.compile(r"\d{4}-\d{2}-\d{2}", re.A)  # an api-version that is not a preview
MEASURED_DAYS = 30  # the most days that a cited measurement covers: the toolbox looks back at most that far


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
    short_undo: str = ""  # a short undo of whole sentences (what to set back, what it does not bring back, where the command is), for a card and a letter, which never cut a command in half: empty when the undo may be cut as it is
    confirm: bool = False  # the change asks once more before the sign-in, although it can be undone: it changes a real resource
    ask: str = ""  # what the person is asked to let Meternaut do, as the end of "You are asked whether to let Meternaut ...": empty when the headline in lower case says it


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
        undo="A deleted public IP address cannot be restored. The address is released and may not be given again. A new one can be made.",
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

# What a resource of each kind that a family changes is called in a sentence of a person: the nouns of the deletes above, and the two kinds that are changed and not deleted. cases/brief.py
# has the same words for every kind of resource that a page names, and a test holds the two together.
NOUNS = {**{kind: wording.noun for kind, wording in DELETE_WORDING.items()}, "microsoft.compute/virtualmachines": "virtual machine", "microsoft.network/p2svpngateways": "point-to-site gateway"}


def noun_of(resource_type: object) -> str:
    """The resource of this type as a noun of a sentence ("disk", "public IP address"); "resource" for a type that no family changes."""
    return NOUNS.get(str(resource_type or "").lower(), "resource")

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
            change=f"Azure deletes the {w.noun} {label} in resource group {group or 'this group'}. Nothing else changes.",
            rechecked=(f"Right before it acts, Meternaut reads the {w.noun} again. It stops unless the {w.noun} is still {w.state}, still tagged as planted by "
                       "Meternaut, still in this resource group and not locked."),
            risk=w.risk, level=w.level, undo=w.brief_undo or w.undo, reversible=False)
    return words


def stop_vm(plan: PlanRecord | None, rtype: str, name: str, group: str) -> Words:
    label = name or "this resource"
    return Words(
        headline=f"Stop (deallocate) the virtual machine {label}{_place(group)}",
        change=(f"Azure stops the virtual machine {label} in resource group {group or 'this group'} and releases its compute. Its disks and any public IP address stay and keep billing. "
                "Nothing else changes."),
        rechecked=("Right before it acts, Meternaut reads the machine again. It stops unless the machine is still running or stopped, still tagged as planted by Meternaut, still in this "
                   "resource group and not locked."),
        risk="Whatever runs on the machine stops. Only its compute is saved. Its disks and any public IP address keep billing.", level="medium",
        undo="Start the machine again, in the Azure portal or with the Azure CLI. A dynamic address may be another one, and a start can fail when the region has no room for the size.",
        reversible=True)


def resize_vm(plan: PlanRecord | None, rtype: str, name: str, group: str) -> Words:
    target = _target(plan)
    was, want = str(target.get("fromVmSize", "")), str(target.get("vmSize", ""))
    was, want = (was if SIZE_NAME.fullmatch(was) else "its size"), (want if SIZE_NAME.fullmatch(want) else "the new size")
    label = name or "this resource"
    return Words(
        headline=f"Resize the virtual machine {label} to {want}{_place(group)}",
        change=f"Azure changes the size of the virtual machine {label} in resource group {group or 'this group'} from {was} to {want}. A running machine restarts. Nothing else changes.",
        rechecked=("Right before it acts, Meternaut reads the machine again. It stops unless the machine still has the same size and is running, stopped or released. It also stops unless the new "
                   "size is still one that it can take, and the machine is still tagged as planted by Meternaut, still in this resource group and not locked."),
        risk="A running machine restarts, and a smaller size has fewer processors and less memory, so a workload that needs them slows down or fails.", level="medium",
        undo=f"Resize the machine back to {was} in the Azure portal or with the Azure CLI. That restarts a running machine again.", reversible=True)


def change_disk_tier(plan: PlanRecord | None, rtype: str, name: str, group: str) -> Words:
    target = _target(plan)
    frm, to = tier_words(target.get("fromSkuName")), tier_words(target.get("skuName"))
    label = name or "this resource"
    return Words(
        headline=f"Move the disk {label} to {to}{_place(group)}",
        change=f"Azure changes the type of the disk {label} in resource group {group or 'this group'} from {frm} to {to}. Nothing else changes.",
        rechecked=("Right before it acts, Meternaut reads the disk again. It stops unless the disk is still the same tier, still unattached (or attached to a machine that is stopped and "
                   "released), still tagged as planted by Meternaut, still in this resource group and not locked."),
        risk="A lower tier has lower limits on operations and throughput, so a workload that needs them slows down.", level="medium",
        undo=f"Change the disk back to {frm} in the Azure portal or with the Azure CLI. It keeps its data. The type can be changed twice a day.", reversible=True)


def _scale_units(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= MAX_SCALE_UNITS else None


def scale_vpn_gateway(plan: PlanRecord | None, rtype: str, name: str, group: str) -> Words:
    target = _target(plan)
    was, want = _scale_units(target.get("fromScaleUnit")), _scale_units(target.get("vpnGatewayScaleUnit"))
    label = name or "this resource"
    old, new = (f"{was} scale units" if was else "its scale units"), (f"{want} scale units" if want else "fewer scale units")
    return Words(
        headline=f"Scale the point-to-site gateway {label} down to {new}{_place(group)}",
        change=(f"Azure changes the scale units of the point-to-site gateway {label} in resource group {group or 'this group'} from {old} to {new}. Users who are connected may be disconnected "
                "while it changes. Nothing else changes."),
        rechecked=(f"Right before it acts, Meternaut reads the gateway and its connection count again. It stops unless the gateway still has {old}, its last operation worked, nobody was "
                   f"connected in the last {CONNECTION_DAYS} days, and it is still tagged as planted by Meternaut, still in this resource group and not locked."),
        risk=("Azure says to plan for downtime when the scale units of a point-to-site gateway change. Users who are connected may be disconnected while it changes, and with fewer scale units "
              "the gateway carries fewer connections and less traffic."), level="medium",
        undo=(f"Set the scale units back to {was or 'what they were'} on the Point to site page of the virtual hub in the Azure portal, or with az network p2s-vpn-gateway update --scale-unit. "
              "That change takes minutes too."),
        reversible=True)


# resource type -> (what the resource is, in a sentence of a person)
TYPE_WORDS = {
    "microsoft.compute/disks": ("Managed disk", "disk"),
    "microsoft.compute/snapshots": ("Snapshot", "snapshot"),
    "microsoft.network/publicipaddresses": ("Public IP address", "public IP address"),
    "microsoft.network/networkinterfaces": ("Network interface", "network interface"),
    "microsoft.network/natgateways": ("NAT gateway", "NAT gateway"),
    "microsoft.network/privateendpoints": ("Private endpoint", "private endpoint"),
    "microsoft.network/loadbalancers": ("Load balancer", "load balancer"),
    "microsoft.network/p2svpngateways": ("Point-to-site gateway", "point-to-site gateway"),
    "microsoft.network/applicationgateways": ("Application gateway", "application gateway"),
    "microsoft.network/azurefirewalls": ("Firewall", "firewall"),
    "microsoft.web/serverfarms": ("App Service plan", "App Service plan"),
    "microsoft.web/sites": ("App Service app", "app"),
    "microsoft.compute/virtualmachines": ("Virtual machine", "virtual machine"),
    "microsoft.compute/virtualmachinescalesets": ("Virtual machine scale set", "virtual machine scale set"),
    "microsoft.storage/storageaccounts": ("Storage account", "storage account"),
    "microsoft.sql/servers/databases": ("SQL database", "SQL database"),
    "microsoft.sql/servers/elasticpools": ("SQL elastic pool", "SQL elastic pool"),
    "microsoft.dbforpostgresql/flexibleservers": ("PostgreSQL server", "PostgreSQL server"),
    "microsoft.dbformysql/flexibleservers": ("MySQL server", "MySQL server"),
    "microsoft.documentdb/databaseaccounts": ("Cosmos DB account", "Cosmos DB account"),
    "microsoft.cache/redis": ("Redis cache", "Redis cache"),
    "microsoft.containerservice/managedclusters": ("Kubernetes cluster", "Kubernetes cluster"),
    "microsoft.eventhub/namespaces": ("Event Hubs namespace", "Event Hubs namespace"),
    "microsoft.servicebus/namespaces": ("Service Bus namespace", "Service Bus namespace"),
    "microsoft.kusto/clusters": ("Data Explorer cluster", "Data Explorer cluster"),
    "microsoft.recoveryservices/vaults": ("Recovery Services vault", "Recovery Services vault"),
    "microsoft.operationalinsights/workspaces": ("Log Analytics workspace", "Log Analytics workspace"),
    "microsoft.cognitiveservices/accounts": ("AI services account", "AI services account"),
    "microsoft.subscriptions/subscriptions": ("Subscription", "subscription"),
    "microsoft.resources/subscriptions/resourcegroups": ("Resource group", "resource group"),
    "microsoft.resources/resourcegroups": ("Resource group", "resource group"),
}
PLAIN_WORD = re.compile(r"[A-Z]?[a-z]+")  # a plain word of a type segment, against an acronym ("IP") or a name that has a capital inside it ("SignalR"), which are kept as they are


def _singular(word: str) -> str:
    """The singular of the last word of a type segment: "hosts" is "host", "policies" is "policy", "addresses" is "address", "prefixes" is "prefix", "searches" is "search" and "caches" is "cache"; a word
    that ends in ss, us or is stays as it is."""
    if word.endswith(("sses", "xes")) or (word.endswith(("ches", "shes")) and not word.endswith("aches")):
        return word[:-2]
    if word.endswith("ies"):
        return word[:-3] + "y"
    return word[:-1] if word.endswith("s") and not word.endswith(("ss", "us", "is")) else word


def type_noun(segment: str) -> str:
    """The noun that the type segment of an id says: its camel case in words, the last one in the singular, an acronym ("IP") and a name with a capital inside it ("signalR" is "SignalR") as they are."""
    pieces = WORD.findall(segment)
    if len(pieces) > 1 and len(pieces[-1]) == 1 and pieces[-1].isupper():
        pieces[-2:] = [pieces[-2] + pieces[-1]]
    names = [piece.lower() if PLAIN_WORD.fullmatch(piece) else piece[:1].upper() + piece[1:] for piece in pieces]
    if PLAIN_WORD.fullmatch(pieces[-1]):
        names[-1] = _singular(names[-1])
    return " ".join(names)


def kind_words(resource_id: object, resource_type: object = "") -> str:
    """The kind of the resource of an id in words of a person: those of the table for a type that has them ("App Service plan"), else the type segment before its name (`bastionHosts` is "bastion host").
    "resource" when the id has no such segment. The brief says a kind in these words too, so that a request of advice and the change that replaces it call a resource the same."""
    known = TYPE_WORDS.get(resource_type.lower()) if isinstance(resource_type, str) else None
    if known:
        return known[1]
    parts = str(resource_id or "").split("/")
    segment = parts[-2] if len(parts) >= 9 else ""
    return type_noun(segment) if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{1,39}", segment) else "resource"


def plan_kind(plan: PlanRecord) -> str:
    """The kind of the resource of a plan of `change-setting` in words of a person: the type that its preconditions keep, else its id."""
    pre = plan.preconditions if isinstance(plan.preconditions, dict) else {}
    return kind_words(plan.resource_id, pre.get("resourceType", ""))


def plan_noun(plan: PlanRecord | None) -> str:
    """The resource of a plan as a noun of a sentence: from the type of its id for the family that works on any kind, else the noun of its kind."""
    if plan is not None and plan.family == "change-setting":
        return plan_kind(plan)
    return noun_of(type_of(plan.family, plan.preconditions)) if plan is not None else "resource"


def _sets(target: dict) -> list[tuple[str, object, object]]:
    """The settings that a plan of `change-setting` changes, as (path, from, to), from its target: a path of plain words and two numbers, at most three."""
    items = target.get("set") if isinstance(target.get("set"), list) else []
    return [(item["path"], item["from"], item["to"]) for item in items[:3] if isinstance(item, dict) and isinstance(item.get("path"), str) and SETTING_PATH.fullmatch(item["path"])
            and all(isinstance(item.get(key), (int, float)) and not isinstance(item.get(key), bool) for key in ("from", "to"))]


def _list(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


ROOT_KEYS = frozenset({"sku"})  # the keys of the root of a resource whose numbers are set there and not under `properties`: the body of the write and the command of the undo use this one test


def at_root(path: str) -> bool:
    """Whether the number of this key path is at the root of the resource (its first key is exactly one of ROOT_KEYS, in any case) and not under `properties`."""
    return path.split(".", 1)[0].lower() in ROOT_KEYS


def raw(number: object) -> str:
    """A number exactly as a command takes it, as JSON writes it: no grouping and no rounding ("1440", "0.125")."""
    return str(number)


def changes_text(target: dict, how: str = "change") -> str:
    """What a plan of `change-setting` changes, from its target: "scale units from 4 to 2 and sku capacity from 8 to 6"; `how` is `back` for how it is put back ("scale units to 4 and sku capacity to 8",
    with the numbers exactly as they were), `now` for what it shows before the change ("scale units at 4") and `new` for what it shows after it ("scale units at 2")."""
    sets = _sets(target)
    say = {"back": lambda path, old, new: f"{label(path)} to {raw(old)}", "now": lambda path, old, new: f"{label(path)} at {value(old)}",
           "new": lambda path, old, new: f"{label(path)} at {value(new)}"}.get(how, lambda path, old, new: f"{label(path)} from {value(old)} to {value(new)}")
    return _list([say(*item) for item in sets]) if sets else "a number"


def measured(pre: dict) -> list[tuple[str, int | float, int]]:
    """The measurements that a plan of `change-setting` cites, from its preconditions, as (name, total, days): a plain metric name, a total that is not below nothing and a window of 1 to MEASURED_DAYS days,
    at most three."""
    items = pre.get("measured") if isinstance(pre.get("measured"), list) else []
    return [(i["name"], i["total"], i["days"]) for i in items if isinstance(i, dict) and isinstance(i.get("name"), str) and METRIC_WORDS.fullmatch(i["name"])
            and isinstance(i.get("total"), (int, float)) and not isinstance(i.get("total"), bool) and i["total"] >= 0 and isinstance(i.get("days"), int) and 0 < i["days"] <= MEASURED_DAYS][:3]


def measured_text(pre: dict) -> str:
    """The measurements that a plan cites, as a clause: "Azure Monitor shows Sessions at 0 over 30 days"; empty when it cites none."""
    return f"Azure Monitor shows {_list([f'{name} at {value(total)} over {days} days' for name, total, days in measured(pre)])}" if measured(pre) else ""


def compared_text(check: object) -> str:
    """What the check after a change of `change-setting` says of the other numbers and flags that were sent, from what it kept: which ones Azure also changed, or that they could not be compared; empty when
    they were compared and none differs. A text is not compared, and the plan says so."""
    if not isinstance(check, dict):
        return ""
    if isinstance(check.get("differences"), str) and check["differences"]:
        return f"Azure also changed: {check['differences']}."
    return "Meternaut could not compare the other numbers and flags with what it sent." if check.get("compared") is False else ""


def setting_words(kind: str, thing: str, group: str, target: dict, pre: dict) -> Words:
    """The words of a plan of `change-setting`, from the kind of the resource, its name and group, and the target and the preconditions of the plan. The pages, the cards, the letters and the record of the
    plan read this one text, so that what a person is shown is what is kept."""
    said, cited = changes_text(target), measured_text(pre)
    api = target.get("apiVersion")
    again = f" It also reads {_list([name for name, _, _ in measured(pre)])} again over the same number of days, and stops if the reading is above what this request was made with." if cited else ""
    command = " ".join(f"{path if at_root(path) else 'properties.' + path}={raw(old)}" for path, old, _ in _sets(target))
    command = f"az resource update --ids <resource id> --set {command}{f' --api-version {api}' if isinstance(api, str) and API_VERSION.fullmatch(api) else ''}" if command else "az resource update"
    back = changes_text(target, "back")
    caveat, pointer = "It does not bring back what the lower number cut off meanwhile.", "The page has the command."
    short = f"Set {back} again in the Azure portal."
    if len(short) + len(caveat) + len(pointer) + 2 > 150:  # a card and a letter have room for three short sentences (a line of a letter holds 160 characters), and a sentence is never cut
        short = "Set the numbers back to what they were in the Azure portal."
    short = f"{short} {caveat} {pointer}"
    return Words(
        headline=f"Scale down the {kind} {thing} in resource group {group}: {said}",
        change=(f"When you approve, Meternaut sends the {kind} {thing} in resource group {group} back to Azure as it was read, with this change, {said}. It uses your own permissions. "
                f"A property that Azure does not show when it is read is not sent, so Meternaut cannot promise that nothing else changes. Afterwards it reads the {kind} again and checks "
                "the number, and that every other number and flag that it sent is still what it sent. It does not compare texts, such as a tier or a name."),
        rechecked=(f"Right before it acts, Meternaut reads the {kind} again. It stops unless the {kind} still shows the old numbers, its last operation worked, it has no lock and no do-not-touch "
                   f"note, and it is in a resource group on the owner's list for real changes.{again}"),
        risk=(f"Meternaut does not know what a lower number takes away from what uses the {kind}. "
              + (f"{cited}, and Meternaut checked that no lock is on the {kind}. " if cited else f"No measurement of its use is cited. It checked that no lock is on the {kind}. ")
              + f"Azure carries out the update in the background and may need minutes: Meternaut follows it for half a minute, and a later check reads the {kind} again. "
              f"If your account may not change the {kind}, Azure refuses and nothing changes."),
        level="medium",
        undo=(f"Set {back} again: on the page of the {kind} in the Azure portal, or with {command}. That update takes minutes too and needs the same right. "
              "Setting it back does not bring back what the lower number cut off meanwhile."),
        reversible=True, short_undo=short, confirm=True, ask=f"scale down the {kind} {thing} in resource group {group} by lowering {said}")


def change_setting(plan: PlanRecord | None, rtype: str, name: str, group: str) -> Words:
    return setting_words(plan_kind(plan) if plan is not None else kind_words("", rtype), name or "this resource", group or "this group", _target(plan),
                         plan.preconditions if plan is not None and isinstance(plan.preconditions, dict) else {})


@dataclass(frozen=True)
class Shown:
    """How one family shows itself to a person. `words` takes the plan (None for a case that has none yet), the type of the resource that the caller knows, the name and the group."""

    words: Callable[[PlanRecord | None, str, str, str], Words]
    called: str  # the change as a noun of a sentence: "The delete was refused or failed ..."
    resource_type: str = ""  # the type that a plan of the family changes when its own preconditions do not say
    saving_level: str = "Expected"  # Verified, Expected or Scenario: only used with a basis of the family's own
    saving_basis: str = ""  # the sentences that say what the figure rests on, when it is not the bill of the last 30 days as it is (the brief says that for a family without one)
    no_figure: str = ""  # why a plan that has no figure claims none
    # The change ends the cost of the resource (a delete, a stop), so that cost lines which show none afterwards are the aim. A change that only lowers the cost (a resize, a change of tier)
    # leaves the resource billing: for it a missing cost line is a line that is not in yet, never "no cost", and a family has to say so to be read the other way.
    cost_ends: bool = False
    summary: str = ""  # what the family does in one phrase, as the function app says it ("delete an unattached managed disk"); the registry checks that it is the family's own
    real: bool = False  # the family changes the owner's real resources (a request about one carries the warning of an automation, and asks once more: `Words.confirm`)


SHOWN: dict[str, Shown] = {
    "delete-disk": Shown(deletes("microsoft.compute/disks"), "delete", "microsoft.compute/disks", cost_ends=True, summary="delete an unattached managed disk"),
    "delete-public-ip": Shown(deletes("microsoft.network/publicipaddresses"), "delete", "microsoft.network/publicipaddresses", cost_ends=True, summary="delete an unassigned public IP address"),
    "stop-vm": Shown(
        stop_vm, "stop", "microsoft.compute/virtualmachines", cost_ends=True, summary="stop a virtual machine and release its compute (deallocate it)",
        saving_basis="It is based on what the machine cost in the last 30 days. Its disks and public IP addresses keep billing, and Meternaut does not count them."),
    "resize-vm": Shown(
        resize_vm, "resize", "microsoft.compute/virtualmachines", saving_level="Scenario", summary="resize a virtual machine to a smaller size of the same series",
        saving_basis=("It assumes that the cost falls with the share of processors that is left in the same size series. Meternaut did not read the price list, so this is an estimate.")),
    "change-disk-tier": Shown(
        change_disk_tier, "change of tier", "microsoft.compute/disks", summary="move a managed disk one tier down (Premium SSD to Standard SSD, Standard SSD to Standard HDD)",
        no_figure="The price of a disk depends on its size and its type, and Meternaut does not read the price list, so it claims no figure for this change."),
    "delete-idle-resource": Shown(deletes(""), "delete", cost_ends=True,
                                  summary="delete a snapshot, a network interface, a NAT gateway, a load balancer or a private endpoint that nothing uses"),
    "scale-vpn-gateway": Shown(
        scale_vpn_gateway, "scale-down", "microsoft.network/p2svpngateways", saving_level="Scenario",
        summary="lower the scale units of a point-to-site gateway by one step (never below 1) when nobody has been connected for days",
        saving_basis="It assumes that the cost falls with the share of scale units that is taken away. Meternaut did not read the price list, so this is an estimate."),
    "change-setting": Shown(
        change_setting, "change", summary="lower a number of a resource, in a group that the owner listed, to a smaller one that a finding proposes", real=True),
}


def kinds() -> dict[str, str]:
    """Every family of change with what it does in one phrase, in the order of the registry: for the page where the owner chooses which kinds of change need two people."""
    return {name: found.summary for name, found in SHOWN.items()}


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
