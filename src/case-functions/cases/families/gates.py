"""The two gates that every change passes, and the third one that a person can close.

AGENTS.md rules 26 (a) and 29: Meternaut changes only waste that it planted itself, in its own resource groups, with the permissions of the person who approves. Reading more
does not widen what may be changed. So every family of change (cases/families/) is held by the same two gates, and a test pins that each family is:

1. the scope: the resource is inside one of the `CHANGE_SCOPES`, a list of Meternaut's OWN resource groups, each in one subscription (loop_config.py; the template gives it exactly the
   one group where Meternaut plants waste of its own);
2. the planted gate: the resource carries the tag that Meternaut put on what it planted (`meternaut-planted`, any value) AND is on the planted list, which is what
   environment/cases/planted.bicep makes: a resource type and a name of the shape `planted-<kind>-<id>` (a test holds this list and the template together). A tag alone is not a
   proof: anybody who may write tags in the group could add it. This gate is the owner's line and it is not loosened for a planted resource that lost its tag. An outside job, which is
   not Meternaut's, takes the tags off the unattached test disks every night at about 22:56 UTC and leaves one tag of its own, so a planted disk that is approved after that night is
   refused here, on purpose, and the request stays open. The action `plant` of the Hub (deploy-hub.yml) puts the planted tags back on every planted disk and public IP address of the
   group, and the page of a request looks at the tag before it offers Approve (cases/precheck.py). So: approve a planted disk the same day it is planted.

The third gate is a person's do-not-touch note (store.do_not_touch). Each gate is checked at three places: when the plan is made, again right before the change with the
approver's token (the family's `recheck`), and in the runner before any call is made.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
GROUP_NAME = re.compile(r"^[A-Za-z0-9._()-]{1,90}$")

# Whether a resource has to be planted by Meternaut, with the tag and on the planted list, before any family may change it. It is True, and it stays True until the owner changes rule 26 (a)
# of AGENTS.md in writing: ONLY THE OWNER MAY CHANGE THIS LINE, in a pull request that he reviews himself. It is not a setting and no environment variable reaches it, so no deployment, no
# agent and no person at the console can turn it off. A test pins it True, and pins this comment.
CHANGE_REQUIRES_PLANTED_TAG = True

# The planted list: the resource types that environment/cases/planted.bicep makes, with the shape of the name that the template gives each (`planted-<kind>-<id>`, the id being the word
# of the planting, 1 to 12 lower-case letters or digits). A type that is not here has no planted resource, so no family changes it. tools/tests/test_environment_template.py holds this list
# and the template together.
PLANTED_NAMES: dict[str, "re.Pattern[str]"] = {
    "microsoft.compute/disks": re.compile(r"planted-(?:disk|osdisk)-[a-z0-9]{1,12}"),
    "microsoft.network/publicipaddresses": re.compile(r"planted-ip-[a-z0-9]{1,12}"),
    "microsoft.compute/virtualmachines": re.compile(r"planted-vm-[a-z0-9]{1,12}"),
    "microsoft.network/networkinterfaces": re.compile(r"planted-nic-[a-z0-9]{1,12}"),
}


@dataclass(frozen=True)
class ChangeScope:
    """One resource group of Meternaut's own, in one subscription: a place where a change may be made."""

    subscription: str  # a subscription id, as the setting spells it (compared without case)
    group: str  # the name of the resource group, as the setting spells it: the address of a call uses this spelling

    @property
    def key(self) -> tuple[str, str]:
        return self.subscription.lower(), self.group.lower()

    def __str__(self) -> str:
        return f"{self.subscription}/{self.group}"


def parse_scopes(text: str) -> tuple[tuple[ChangeScope, ...], list[str]]:
    """The scopes of a setting like `<subscription id>/<resource group>,<subscription id>/<resource group>`, and what is wrong with it.

    Every entry is one subscription id (a GUID) and one resource group name, and nothing else: no wildcard, no empty entry, no scope twice. The list is never empty."""
    scopes: list[ChangeScope] = []
    problems: list[str] = []
    for position, entry in enumerate(part.strip() for part in (text or "").split(",")):
        subscription, slash, group = entry.partition("/")
        if not slash or not GUID.fullmatch(subscription) or not GROUP_NAME.fullmatch(group):
            problems.append(f"entry {position + 1} is not <subscription id>/<resource group>")
            continue
        scope = ChangeScope(subscription.lower(), group)
        if scope.key in {s.key for s in scopes}:
            problems.append(f"entry {position + 1} repeats an earlier one")
            continue
        scopes.append(scope)
    if not scopes and not problems:
        problems.append("it holds no scope")
    return tuple(scopes), problems


def scope_of(scopes: Sequence[ChangeScope], subscription_id: str | None, resource_group: str | None) -> ChangeScope | None:
    """The scope that holds a resource of this subscription and this group, or None. Both have to match, without case: a group of the same name in another subscription is not it."""
    wanted = ((subscription_id or "").lower(), (resource_group or "").lower())
    if not wanted[0] or not wanted[1]:
        return None
    return next((scope for scope in scopes if scope.key == wanted), None)


def why_outside(scopes: Sequence[ChangeScope], subscription_id: str | None, resource_group: str | None) -> str | None:
    """None when the resource is inside a scope; else the plain reason why not. The words say "the one" while there is one scope, as they always did."""
    if not subscription_id:
        return "the resource has no subscription id"
    single = len(scopes) == 1
    if not any(scope.subscription.lower() == subscription_id.lower() for scope in scopes):
        return "the resource is outside the one subscription in which a change may be made" if single else "the resource is outside the subscriptions in which a change may be made"
    if scope_of(scopes, subscription_id, resource_group) is None:
        return "the resource is outside the one resource group in which a change may be made" if single else "the resource is outside the resource groups in which a change may be made"
    return None


def has_tag(tags: Mapping[str, object] | None, tag: str) -> bool:
    """Whether the tag is on the resource with a value (the name compares without case; a value of blanks is no value)."""
    return any(str(key).lower() == tag.lower() and str(value).strip() for key, value in (tags or {}).items())


def on_planted_list(resource_type: str, name: str) -> bool:
    """Whether the resource is one of what environment/cases/planted.bicep makes: its type is a planted type and its name has the shape of the template's names."""
    shape = PLANTED_NAMES.get((resource_type or "").lower())
    return shape is not None and shape.fullmatch((name or "").lower()) is not None


def why_not_planted(tags: Mapping[str, object] | None, resource_type: str, name: str, tag: str) -> str | None:
    """None when the resource is planted by Meternaut (the tag, and the planted list); else the plain reason why not. While CHANGE_REQUIRES_PLANTED_TAG is True, nothing else passes."""
    if not CHANGE_REQUIRES_PLANTED_TAG:
        return None
    if not has_tag(tags, tag):
        return f"the resource does not carry the {tag} tag"
    if not on_planted_list(resource_type, name):
        return "the resource is not on the list of what Meternaut planted: its type and its name are not ones that the planting makes"
    return None


@dataclass(frozen=True)
class Gates:
    """What a family needs to know about the places and the mark that a change may be made on: the scopes and the planted tag."""

    scopes: tuple[ChangeScope, ...]
    planted_tag: str = "meternaut-planted"

    def scope_of(self, subscription_id: str | None, resource_group: str | None) -> ChangeScope | None:
        return scope_of(self.scopes, subscription_id, resource_group)

    def why_outside(self, subscription_id: str | None, resource_group: str | None) -> str | None:
        return why_outside(self.scopes, subscription_id, resource_group)

    def why_not_planted(self, tags: Mapping[str, object] | None, resource_type: str, name: str) -> str | None:
        return why_not_planted(tags, resource_type, name, self.planted_tag)
