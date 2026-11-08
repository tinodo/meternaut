"""Which subscriptions one run of the Watch reads.

With SCOPE_ALL_SUBSCRIPTIONS on, the answer is every subscription that the app's own identity can read: the list that Azure Resource Manager gives it, made once at the start of
a run. So the Watch reads as much of the estate as a person has given the identity roles for (Reader and Cost Management Reader, at a subscription or at a management group above
it) and no more, and the app grants itself nothing. Only a subscription in the state Enabled is read; the ids are lower case, sorted and counted once; and a run reads at most
MAX_SUBSCRIPTIONS of them, which is what one Resource Graph query takes.

When the list cannot be had, or has no subscription in it, the run reads the subscriptions of SCOPE_SUBSCRIPTIONS and says so. With no such list it does not run: the History says
why, and a run never watches nothing without saying so. With the switch off, only SCOPE_SUBSCRIPTIONS is read.

Nothing here changes what a change may touch: plans and changes are keyed on the one subscription and group of the loop (CHANGE_SUBSCRIPTION_ID, CHANGE_RESOURCE_GROUP), whatever
the Watch reads.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Callable

from .arm import Arm
from .config import GUID, Settings
from .http import HttpError
from .identity import IdentityError

MAX_SUBSCRIPTIONS = 1000
ENABLED = "enabled"
SUBSCRIPTION_ID = re.compile(r"^/subscriptions/([0-9a-fA-F-]{36})$")

SOURCE_ESTATE = "estate"  # every subscription that the identity can read
SOURCE_SETTING = "setting"  # the subscriptions of SCOPE_SUBSCRIPTIONS
SOURCE_FALLBACK = "setting-fallback"  # the same, because the list of the identity could not be used


class ScopeError(Exception):
    """There is nothing to read; the text says why, in plain words."""


@dataclass(frozen=True)
class Scope:
    subscriptions: tuple[str, ...]
    source: str
    notes: tuple[str, ...] = ()
    quotas: tuple[str, ...] = ()  # the quota ids of the subscriptions (subscriptionPolicies.quotaId of the list), which the capability profile reads a hint of the agreement from


def _id_of(item: dict) -> str | None:
    """The lower-case id of one subscription of the list, or None when it has none that is a GUID."""
    value = item.get("subscriptionId")
    if not isinstance(value, str):
        found = SUBSCRIPTION_ID.match(str(item.get("id") or ""))
        value = found.group(1) if found else None
    return value.strip().lower() if isinstance(value, str) and GUID.match(value.strip()) else None


def readable(items: list[dict]) -> list[str]:
    """The ids of the subscriptions of the list whose state is Enabled, lower case, sorted, each once."""
    ids = {sub for item in items if str(item.get("state") or "").strip().lower() == ENABLED for sub in (_id_of(item),) if sub}
    return sorted(ids)


def quota_ids(items: list[dict], subscriptions: tuple[str, ...]) -> tuple[str, ...]:
    """The quota id of each of these subscriptions that the list gives one for (Learn, "Subscriptions - List": subscriptionPolicies.quotaId), one for each subscription."""
    wanted = set(subscriptions)
    found: dict[str, str] = {}
    for item in items:
        policies = item.get("subscriptionPolicies")
        sub = _id_of(item)
        if sub in wanted and isinstance(policies, dict) and isinstance(policies.get("quotaId"), str) and policies["quotaId"].strip():
            found.setdefault(sub, policies["quotaId"].strip()[:60])
    return tuple(found[sub] for sub in sorted(found))


def resolve(arm: Arm, settings: Settings, keep: str | None = None, redact: Callable[[object], str] = str) -> Scope:
    """The subscriptions that a run reads, with the notes that the History carries. Raises ScopeError when there are none.

    `keep` is a subscription that stays in the list when the list has to be cut at MAX_SUBSCRIPTIONS (the one where Meternaut plants its own waste: the loop is proved there).
    `redact` cleans the text of an error before it is part of a note."""
    explicit = tuple(dict.fromkeys(settings.subscriptions))
    if not settings.all_subscriptions:
        if not explicit:
            raise ScopeError("no subscription is named: SCOPE_SUBSCRIPTIONS is empty and SCOPE_ALL_SUBSCRIPTIONS is off")
        return Scope(explicit, SOURCE_SETTING)
    try:
        items = arm.subscriptions()
        ids = readable(items)
    except (HttpError, IdentityError) as error:
        why = f"the list of the subscriptions that the identity can read could not be had ({redact(error)})"
    else:
        if ids:
            scope = _cut(ids, keep)
            return replace(scope, quotas=quota_ids(items, scope.subscriptions))
        why = "the identity can read no subscription that is enabled"
    if explicit:
        return Scope(explicit, SOURCE_FALLBACK, (f"{why}, so the {len(explicit)} subscription{'' if len(explicit) == 1 else 's'} of SCOPE_SUBSCRIPTIONS "
                                                 f"{'is' if len(explicit) == 1 else 'are'} read instead",))
    raise ScopeError(f"{why}, and SCOPE_SUBSCRIPTIONS is empty, so there is nothing to read")


def _cut(ids: list[str], keep: str | None) -> Scope:
    if len(ids) <= MAX_SUBSCRIPTIONS:
        return Scope(tuple(ids), SOURCE_ESTATE)
    chosen = ids[:MAX_SUBSCRIPTIONS]
    must = keep.strip().lower() if keep else None
    which = f"the first {MAX_SUBSCRIPTIONS} by id"
    if must and must in ids and must not in chosen:
        chosen = sorted([*chosen[:MAX_SUBSCRIPTIONS - 1], must])
        which = f"the first {MAX_SUBSCRIPTIONS - 1} by id and the one where Meternaut plants its own waste"
    return Scope(tuple(chosen), SOURCE_ESTATE, (f"the identity can read {len(ids)} subscriptions and one query takes at most {MAX_SUBSCRIPTIONS}: "
                                                f"{which} are read, the other {len(ids) - MAX_SUBSCRIPTIONS} are not",))
