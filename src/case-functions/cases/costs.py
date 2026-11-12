"""What the cost of a finding says: how it was read, what it is the sum of, and where to look at it in the Azure portal.

The reads (arm.py, detectors.py, run.py), the records (models.py) and the decision brief (brief.py) share these words and shapes, so that a page, a letter and a card say the same thing
about the same state. Standard library only.

The 30-day cost of a finding is what Cost Management shows for the scope that the finding is about, as the actual cost (what is billed), over the 30 closed days:
  - a resource: the cost lines of its own id (Cost Management gives ids in lower case, and every match here is made in lower case);
  - a resource group: every cost line of the group;
  - a subscription: every cost line of the subscription, also the ones that no resource and no resource group have (a plan of Microsoft Defender for Cloud, a purchase).
"""
from __future__ import annotations

import math
import re
from typing import Mapping, NamedTuple
from urllib.parse import quote

# How the 30-day cost of a finding was read (CaseRecord.cost_state). A record that was written before the state existed has none ("") and is read by cases/brief.py (cost_state_of).
LINES = "lines"  # Cost Management has cost lines for the scope, and `cost_usd_30d` is their sum (it may be zero: a line can cost nothing)
NONE = "none"  # the read worked and Azure has no cost line for the scope; `cost_usd_30d` is 0.0, as it always was for this case
FAILED = "failed"  # the read did not work: Azure said "too many requests" for as long as the app was willing to wait, or answered with an error; `cost_usd_30d` is None
CURRENCY = "currency"  # the cost lines are not in US dollars, so no figure is shown in dollars; `cost_usd_30d` is None
STATES = (LINES, NONE, FAILED, CURRENCY)

# The words of each state, as the figure of a request says them under "Cost not visible". Said once here, for the page, the letter and the card.
UNREAD_WORDS = "No cost line was read yet."
NO_LINE_WORDS = "Azure has no cost line for this yet."
ZERO_WORDS = "Cost Management shows no cost for this in the last 30 days."
FAILED_WORDS = "Cost could not be read just now."
CURRENCY_WORDS = "The cost lines are not in US dollars."
STATE_WORDS = {"": UNREAD_WORDS, NONE: NO_LINE_WORDS, LINES: ZERO_WORDS, FAILED: FAILED_WORDS, CURRENCY: CURRENCY_WORDS}
# The states in the order in which they decide what a figure of several findings says: a read that failed is told first, and a cost of nothing that Cost Management showed last.
SAYS_FIRST = (FAILED, CURRENCY, "", NONE, LINES)


def state_words(state: str, many: bool = False) -> str:
    """What the figure of a request says when it shows no cost, for a cost that was read in this state; `many` for the row that stands for several findings ("for these" and not "for this")."""
    text = STATE_WORDS.get(state, UNREAD_WORDS)
    return text.replace(" for this ", " for these ") if many else text


def worst_state(states: "list[str] | tuple[str, ...]") -> str:
    """The state that says what a figure of several findings has to say about the cost that none of them shows: the first of SAYS_FIRST that one of them is in."""
    return next((state for state in SAYS_FIRST if state in states), "")

GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
TOP_SERVICES = 3  # the services that "Made of" names: the largest ones
MAX_SERVICE = 60  # the characters of the name of a service that a record keeps

PORTAL = "https://portal.azure.com"
# Learn, "Save and share customized views" (read on 2026-11-12): the address of Cost analysis for a scope is the portal, then
# #blade/Microsoft_Azure_CostManagement/Menu/open/costanalysis/scope/<the Resource Manager id of the scope, URL encoded>. Without a view the built-in view of accumulated cost opens.
ANALYSIS = "/#blade/Microsoft_Azure_CostManagement/Menu/open/costanalysis/scope/"


class Scope(NamedTuple):
    """What an Azure id is the id of: `kind` is subscription, group, resource or "" (not an Azure id), with the subscription (lower case) and the resource group that it names ("" when none)."""

    kind: str
    subscription: str
    group: str


def scope_of(resource_id: object) -> Scope:
    """The scope that an id names: a subscription, a resource group, or a resource (anything below a resource group, or below a subscription). The case of the id does not matter."""
    parts = str(resource_id or "").strip().rstrip("/").split("/")  # ["", "subscriptions", <id>, "resourcegroups", <group>, "providers", ...]
    if len(parts) < 3 or parts[0] or parts[1].lower() != "subscriptions" or not re.fullmatch(GUID, parts[2]):
        return Scope("", "", "")
    subscription = parts[2].lower()
    if len(parts) == 3:
        return Scope("subscription", subscription, "")
    if parts[3].lower() == "resourcegroups" and len(parts) >= 5 and parts[4]:
        return Scope("group" if len(parts) == 5 else "resource", subscription, parts[4])
    return Scope("resource", subscription, "")


def is_container(resource_id: object) -> bool:
    """Whether an id is the id of a subscription or of a resource group: what a finding about it costs is the sum of every cost line in it, and not the lines of one id."""
    return scope_of(resource_id).kind in ("subscription", "group")


def container_key(resource_id: object) -> str:
    """The id of the subscription or of the resource group that an id is the id of, in lower case (the key that the cost of a container is kept under); empty for any other id."""
    scope = scope_of(resource_id)
    if scope.kind == "subscription":
        return f"/subscriptions/{scope.subscription}"
    return f"/subscriptions/{scope.subscription}/resourcegroups/{scope.group.lower()}" if scope.kind == "group" else ""


GROUP_NAME = re.compile(r"[-\w.()]{1,90}")  # Learn, "Resource naming restrictions": up to 90 letters, digits, underscores, hyphens, periods and round brackets, and no period at the end


def valid_group(name: object) -> bool:
    """Whether a text can be the name of a resource group (Azure's own rule): a link is made from a name that can, and from nothing else."""
    return isinstance(name, str) and GROUP_NAME.fullmatch(name) is not None and not name.endswith(".")


def analysis_url(subscription: object, group: object = "") -> str:
    """The address of Cost analysis in the Azure portal for a subscription, or for a resource group of it when `group` is given. Empty when the subscription is not an id, or the name of the group
    cannot be one: a link is made from ids that code has checked, never from text."""
    sub = str(subscription or "").strip()
    if not re.fullmatch(GUID, sub):
        return ""
    name = str(group or "").strip()
    if name and not valid_group(name):
        return ""
    scope = f"/subscriptions/{sub.lower()}" + (f"/resourceGroups/{name}" if name else "")
    return f"{PORTAL}{ANALYSIS}{quote(scope, safe='')}"


def _amount(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def parts_of(by_service: Mapping[str, float]) -> dict:
    """What a cost is made of, as a record keeps it: the TOP_SERVICES largest services with their cost, and how many more there are and what they cost together. Empty when no service has a cost
    that is above nothing. A service with no name is "Other". The numbers are those of the cost lines, in US dollars, to a cent."""
    merged: dict[str, float] = {}
    for name, amount in by_service.items():
        number = _amount(amount)
        if number is not None:
            label = " ".join(str(name or "").split())[:MAX_SERVICE] or "Other"
            merged[label] = merged.get(label, 0.0) + number
    ranked = sorted(((name, amount) for name, amount in merged.items() if round(amount, 2) > 0), key=lambda item: (-item[1], item[0]))
    if not ranked:
        return {}
    top = ranked[:TOP_SERVICES]
    rest = round(sum(merged.values()) - sum(amount for _, amount in top), 2)
    return {"services": [[name, round(amount, 2)] for name, amount in top], "more": len(merged) - len(top), "moreUsd": rest if rest > 0 else 0.0}


def valid_parts(value: object) -> dict:
    """The parts that a record holds, when they are what parts_of makes; an empty dict otherwise (a record that is damaged shows less and never something else)."""
    if not isinstance(value, dict) or not isinstance(value.get("services"), list) or not 1 <= len(value["services"]) <= TOP_SERVICES:
        return {}
    services: list[list] = []
    for item in value["services"]:
        if not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], str) or not item[0].strip() or _amount(item[1]) is None or item[1] <= 0:
            return {}
        services.append([item[0][:MAX_SERVICE], float(item[1])])
    more, more_usd = value.get("more"), _amount(value.get("moreUsd"))
    if isinstance(more, bool) or not isinstance(more, int) or not 0 <= more <= 100000 or more_usd is None or more_usd < 0:
        return {}
    return {"services": services, "more": more, "moreUsd": more_usd}
