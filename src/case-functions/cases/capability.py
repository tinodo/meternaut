"""The capability profile: what the app's own identity can see of an estate's agreement and commitments (docs/proposals/15-learning.md).

What a finding can say depends on what the identity can see. With no right to list reservations, "this estate has no reservation" is something that Meternaut does not know, and an advice to buy
one would be a guess. So each investigation reads, once, the lists that say what the identity may see, and keeps the answer as words of a closed list (`CapabilityRecord`: no id, no name and no
address of an estate, and nothing that a person or the estate wrote):

* `visible`: the read answered and listed something (or, for the cost lines, at least one subscription was read).
* `not visible with this access`: Azure refused the read (401 or 403), or answered with an empty list. These lists hold only what the caller may see, so an empty one says nothing about what
  exists, and it is never reported as "none".
* `unavailable`: the read failed in another way (a limit, a fault, a service that does not answer), or the cost lines of every subscription could not be read.
* `unknown`: the read was not made.

The reads are the first page of the lists of billing accounts (which also give the agreement type: Learn, "Billing Accounts - List"), reservation orders ("Reservation Order - List") and savings plan
orders ("Savings Plan Order - List"), one line of the price sheet of the first subscription ("Price Sheet - Get"), and the quota ids of the subscriptions, which the list of subscriptions already
gives ("Subscriptions - List"): a hint of the agreement when no billing account is visible. Nothing here asks for more access: it says what the access that people gave comes to.

What it is used for: the tool `commitments` says, next to the recommendations of the platform, what this identity can see of reservations, savings plans, the price sheet and the agreement, so that
no model reads an empty list as "none"; and a finding about a commitment that does not fit the use carries, in the decision brief, the one sentence that says what the access cannot see (`access_code`).
No model reads the profile as text, and no model calls are made here.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Iterable, Mapping, Sequence

from .http import HttpError
from .identity import IdentityError
from .memory_store import stamp
from .models import CapabilityRecord, Store, StoreError
from .ownership import NOT_VISIBLE

LOG = logging.getLogger("meternaut.capability")

VISIBLE = "visible"
UNAVAILABLE = "unavailable"
UNKNOWN = "unknown"
REFUSED = (401, 403)
WORDS = (VISIBLE, NOT_VISIBLE, UNAVAILABLE, UNKNOWN)

# properties.agreementType of a billing account (Learn, "Billing Accounts - List"), compared without case or punctuation.
AGREEMENTS = {"enterpriseagreement": "enterprise", "microsoftcustomeragreement": "customer", "microsoftonlineservicesprogram": "pay-as-you-go", "microsoftpartneragreement": "partner"}
AGREEMENT_WORDS = ("enterprise", "customer", "pay-as-you-go", "partner", "other", "mixed", UNKNOWN)
# What the quota ids of the subscriptions suggest (Learn, "Understand Cost Management data", "Supported Microsoft Azure offers"): EnterpriseAgreement_2014-09-01 is the quota id of an Enterprise
# Agreement offer and of the Microsoft Azure Plan of a Microsoft Customer Agreement alike, so the two cannot be told apart by it; the quota ids of the partner offers start with CSP; and
# MSDNDevTest_2014-09-01 is shared by offers of three agreements, so it says nothing.
HINT_WORDS = ("pay-as-you-go", "enterprise-or-customer", "partner", "other", "mixed", UNKNOWN)
COMMITMENT_BASIS = "commitment-misfit"  # the one basis of agents.BASES that rests on the commitments that the identity can see

# Learn, "What are savings plans?" (2026-10-29): savings plans are available to organizations with an Enterprise Agreement, a Microsoft Customer Agreement or a Microsoft Partner Agreement.
NOT_OFFERED = ("pay-as-you-go",)


def _read(call):
    """(the word for how the read went, what it returned). It never raises: a probe is a convenience, and one that fails never stops a run."""
    try:
        return VISIBLE, call()
    except HttpError as error:
        return (NOT_VISIBLE if error.status in REFUSED else UNAVAILABLE), None
    except IdentityError:
        return UNAVAILABLE, None
    except Exception as error:  # noqa: BLE001 (the arm of a test, a shape that Azure changed: the word is unavailable and the run goes on)
        LOG.warning("capability: a probe failed (%s)", type(error).__name__)
        return UNAVAILABLE, None


def _listed(call) -> tuple[str, list[dict]]:
    """A list that holds only what the caller may see: visible with its items, and never "none" for an empty one."""
    state, items = _read(call)
    if state != VISIBLE:
        return state, []
    found = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    return (VISIBLE, found) if found else (NOT_VISIBLE, [])


def agreement_of(accounts: Iterable[object]) -> str:
    """The agreement type that the billing accounts report, as a word of AGREEMENT_WORDS: one word when they all say the same, `mixed` when they differ, `unknown` when none says."""
    words = set()
    for account in accounts:
        properties = account.get("properties") if isinstance(account, dict) else None
        text = properties.get("agreementType") if isinstance(properties, dict) else None
        key = re.sub(r"[^a-z]", "", text.lower()) if isinstance(text, str) else ""
        if key:
            words.add(AGREEMENTS.get(key, "other"))
    return UNKNOWN if not words else next(iter(words)) if len(words) == 1 else "mixed"


def hint_of(quota_ids: Iterable[object]) -> str:
    """What the quota ids suggest of the agreement, as a word of HINT_WORDS: one word when they all suggest the same, `mixed` when they differ, `unknown` when there is none."""
    words = set()
    for quota in quota_ids:
        if not isinstance(quota, str) or not quota.strip():
            continue
        key = re.sub(r"[^a-z]", "", quota.split("_", 1)[0].lower())
        words.add("pay-as-you-go" if key == "payasyougo" else "enterprise-or-customer" if key == "enterpriseagreement" else "partner" if key.startswith("csp") else "other")
    return UNKNOWN if not words else next(iter(words)) if len(words) == 1 else "mixed"


def probe(arm: object, subscriptions: Sequence[str], quota_ids: Iterable[object], contexts: Mapping[str, object], run_id: str, now: dt.datetime) -> CapabilityRecord:
    """What the identity can see in this run. It never raises. `quota_ids` are those that the one list of subscriptions of the run gave (scope.py), so that the list is not asked for again, and
    `contexts` are what the Watch read of each subscription: the cost lines were visible when at least one of them was read."""
    subs = tuple(subscriptions)
    cost = UNKNOWN
    if contexts:
        cost = VISIBLE if any(getattr(context, "costs", None) is not None for context in contexts.values()) else UNAVAILABLE
    billing, accounts = _listed(arm.billing_accounts)  # type: ignore[attr-defined]
    reservations, _ = _listed(arm.reservation_orders)  # type: ignore[attr-defined]
    plans, _ = _listed(arm.savings_plan_orders)  # type: ignore[attr-defined]
    sheet = _read(lambda: arm.price_sheet(subs[0]))[0] if subs else UNKNOWN  # type: ignore[attr-defined]
    return CapabilityRecord(run_id=run_id, at=stamp(now), subscriptions=len(subs), cost=cost, billing=billing, agreement=agreement_of(accounts), hint=hint_of(quota_ids), reservations=reservations,
                            savings_plans=plans, price_sheet=sheet)


def keep(store: Store | None, profile: CapabilityRecord) -> CapabilityRecord:
    """The profile goes to the store, one for each run. A store that fails never stops the run."""
    if store is not None:
        try:
            store.profile_put(profile)
        except StoreError as error:
            LOG.warning("capability: the profile could not be kept (%s)", type(error).__name__)
    return profile


def _word(value: object, allowed: Sequence[str]) -> str:
    return value if isinstance(value, str) and value in allowed else UNKNOWN


def words_of(profile: CapabilityRecord) -> dict[str, str]:
    """What the tool `commitments` shows of the profile: four words, each from a closed list."""
    return {"reservations": _word(profile.reservations, WORDS), "savings_plans": _word(profile.savings_plans, WORDS), "price_sheet": _word(profile.price_sheet, WORDS),
            "agreement": _word(profile.agreement, AGREEMENT_WORDS)}


def access_code(profile: CapabilityRecord | None, basis: str) -> str | None:
    """The key of brief.ACCESS_WORDS that applies to a finding of this basis, or None. Only a finding about a commitment that does not fit the use rests on what the identity can see of
    reservations and savings plans, and only a refusal counts: a read that failed says nothing about the access. Under an agreement that does not offer savings plans, that part is no matter of
    access."""
    if profile is None or basis != COMMITMENT_BASIS:
        return None
    reservations = profile.reservations == NOT_VISIBLE
    plans = profile.savings_plans == NOT_VISIBLE
    if profile.agreement in NOT_OFFERED:
        return "reservations-not-visible" if reservations else "savings-plans-not-offered"
    if reservations and plans:
        return "commitments-not-visible"
    return "reservations-not-visible" if reservations else "savings-plans-not-visible" if plans else None
