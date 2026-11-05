"""The guards: facts that code reads from the estate and that a model's answer cannot lift."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .detectors import Context, Lead

RECENT_DAYS = 7
KEEP_KEYS = frozenset({"donotdelete", "keep", "meternautkeep", "preserve", "donotremove", "nodelete"})
NOT_SET = frozenset({"", "false", "no", "0", "none", "n"})
MANAGED_PREFIXES = ("mc_", "databricks-rg-", "networkwatcherrg", "defaultresourcegroup-", "cloud-shell-storage-", "azurebackuprg_",
                    "loganalyticsdefaultresources", "ma_", "synapseworkspace-managedrg-")

# flag name in the prompt, name in the History
NAMES = (("locked", "locked"), ("keepTag", "keep-tag"), ("tooNew", "too-new"), ("managedGroup", "managed-group"), ("unverified", "unverified"))


@dataclass(frozen=True)
class Guards:
    flags: dict[str, bool]

    @property
    def names(self) -> list[str]:
        """The guards that are on, as the History names them."""
        return [text for flag, text in NAMES if self.flags.get(flag)]


def keep_tag(tags: dict[str, str]) -> bool:
    for key, value in tags.items():
        if re.sub(r"[^a-z0-9]", "", key.lower()) in KEEP_KEYS and str(value).strip().lower() not in NOT_SET:
            return True
    return False


def is_locked(resource_id: str, scopes: list[str]) -> bool:
    target = resource_id.lower().rstrip("/")
    return any(target == scope or target.startswith(scope + "/") for scope in scopes)


def evaluate(lead: Lead, context: Context, scope_locks: list[str] | None, fixture: bool = False) -> Guards:
    """A guard that cannot be read is a guard that is on: "unverified" stops a lead as much as a lock does.

    `scope_locks` are the locks that the list of the lead's own scopes returned; None means that they could not be read.
    `fixture` is a resource that Meternaut planted itself in the group where its writer may act: it is not held back for being new, and no other guard is lifted.
    """
    target = lead.resource_id.lower()
    unverified = context.locks is None or context.recent is None or context.managed_groups is None or scope_locks is None
    locked = is_locked(lead.resource_id, (context.locks or []) + (scope_locks or []))
    too_new = not fixture and ((lead.age_days is not None and lead.age_days < RECENT_DAYS) or (context.recent is not None and target in context.recent))
    group = lead.resource_group.lower()
    managed = bool(lead.managed_by) or group.startswith(MANAGED_PREFIXES) or (context.managed_groups is not None and group in context.managed_groups)
    return Guards({"locked": locked, "keepTag": keep_tag(lead.tags), "tooNew": too_new, "managedGroup": managed, "unverified": unverified})
