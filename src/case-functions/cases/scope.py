"""Which subscriptions one run of the Watch reads.

With SCOPE_ALL_SUBSCRIPTIONS on, the answer is every subscription that the app's own identity can read: the list that Azure Resource Manager gives it, made once at the start of
a run. So the Watch reads as much of the estate as a person has given the identity roles for (Reader and Cost Management Reader, at a subscription or at a management group above
it) and no more, and the app grants itself nothing. Only a subscription in the state Enabled is read; the ids are lower case, sorted and counted once; and a run reads at most
MAX_SUBSCRIPTIONS of them, which is what one Resource Graph query takes.

When the list cannot be had, or has no subscription in it, the run reads the subscriptions of SCOPE_SUBSCRIPTIONS and says so. With no such list it does not run: the History says
why, and a run never watches nothing without saying so. With the switch off, only SCOPE_SUBSCRIPTIONS is read.

Nothing here changes what a change may touch: plans and changes are keyed on the resource groups of the change scopes (CHANGE_SCOPES), whatever the Watch reads.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

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


def resolve(arm: Arm, settings: Settings, keep: "str | Iterable[str] | None" = None, redact: Callable[[object], str] = str) -> Scope:
    """The subscriptions that a run reads, with the notes that the History carries. Raises ScopeError when there are none.

    `keep` is a subscription, or several, that stay in the list when the list has to be cut at MAX_SUBSCRIPTIONS (the ones where Meternaut plants its own waste: the loop is proved there).
    `redact` cleans the text of an error before it is part of a note."""
    explicit = tuple(dict.fromkeys(settings.subscriptions))
    if not settings.all_subscriptions:
        if not explicit:
            raise ScopeError("no subscription is named: SCOPE_SUBSCRIPTIONS is empty and SCOPE_ALL_SUBSCRIPTIONS is off")
        return Scope(explicit, SOURCE_SETTING)
    try:
        ids = readable(arm.subscriptions())
    except (HttpError, IdentityError) as error:
        why = f"the list of the subscriptions that the identity can read could not be had ({redact(error)})"
    else:
        if ids:
            return _cut(ids, keep)
        why = "the identity can read no subscription that is enabled"
    if explicit:
        return Scope(explicit, SOURCE_FALLBACK, (f"{why}, so the {len(explicit)} subscription{'' if len(explicit) == 1 else 's'} of SCOPE_SUBSCRIPTIONS "
                                                 f"{'is' if len(explicit) == 1 else 'are'} read instead",))
    raise ScopeError(f"{why}, and SCOPE_SUBSCRIPTIONS is empty, so there is nothing to read")


def _cut(ids: list[str], keep: "str | Iterable[str] | None") -> Scope:
    if len(ids) <= MAX_SUBSCRIPTIONS:
        return Scope(tuple(ids), SOURCE_ESTATE)
    chosen = ids[:MAX_SUBSCRIPTIONS]
    wanted = [keep] if isinstance(keep, str) else list(keep or ())
    must = {sub.strip().lower() for sub in wanted if sub and sub.strip()}
    which = f"the first {MAX_SUBSCRIPTIONS} by id"
    missing = sorted(sub for sub in must if sub in ids and sub not in chosen)
    if missing:
        chosen = sorted([*chosen[:MAX_SUBSCRIPTIONS - len(missing)], *missing])
        which = (f"the first {MAX_SUBSCRIPTIONS - len(missing)} by id and the {'one' if len(missing) == 1 else 'ones'} where Meternaut plants its own waste")
    return Scope(tuple(chosen), SOURCE_ESTATE, (f"the identity can read {len(ids)} subscriptions and one query takes at most {MAX_SUBSCRIPTIONS}: "
                                                f"{which} are read, the other {len(ids) - MAX_SUBSCRIPTIONS} are not",))
