"""What a Watch keeps right on the findings that wait for a person, and the findings that it holds back.

A finding is made into a request only when it can say what to look at (brief.says_nothing): the request of a finding that cannot is never made, and one that was made before is taken back. Both
are said in the History with the reason `held back: nothing to say` and counted in the run. The Watch also gives a finding that has an open request what it has learned about it since the
request was made (the name of its subscription, the words of Advisor, what it costs), so that a request made by an earlier version shows what a request made now shows.

Nothing here changes Azure. It reads and writes the records of the app only.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Sequence

from . import brief
from . import costs as cost_words
from .approvals import HELD_BACK, NOTHING_TO_SAY
from .detectors import Lead
from .events import History
from .models import CaseRecord, StoreError
from .roles import clean_text


def cost_fields(lead: Lead, old: CaseRecord | None) -> dict:
    """What a case keeps of the cost that the lead says, as the fields of the record. A read that failed this time (the lead's state is FAILED) keeps what an earlier read of the same case
    found, so that one run that Azure turned away does not take a figure from a request that has one: the state FAILED is for a case that never had a figure."""
    if lead.cost_state == cost_words.FAILED and old is not None and old.cost_usd_30d is not None:
        return {"cost_usd_30d": old.cost_usd_30d, "cost_state": old.cost_state, "cost_by_service": old.cost_by_service, "estimate": old.estimate}
    return {"cost_usd_30d": lead.cost_usd_30d, "cost_state": lead.cost_state, "cost_by_service": lead.cost_by_service, "estimate": lead.estimate}


def _brought_up(kept: CaseRecord, lead: Lead) -> CaseRecord | None:
    """The case as it is when it holds what the lead says now: the name of the subscription, the words of Advisor and, when this Watch could read the cost (lines, none or not in dollars), the cost.
    None when it holds that already."""
    changes: dict = {}
    if lead.subscription_name and kept.subscription_name != lead.subscription_name:
        changes["subscription_name"] = lead.subscription_name
    if lead.advice and kept.advice != lead.advice:
        changes["advice"] = lead.advice
    if lead.cost_state in (cost_words.LINES, cost_words.NONE, cost_words.CURRENCY):
        wanted = {"cost_usd_30d": lead.cost_usd_30d, "cost_state": lead.cost_state, "cost_by_service": lead.cost_by_service, "estimate": lead.estimate if lead.cost_state == cost_words.NONE else {}}
        if lead.cost_state == cost_words.NONE and kept.cost_state == cost_words.NONE:
            del wanted["cost_usd_30d"]  # no cost line is 0.0 or no number at all (a subscription that has no line anywhere): the two say the same, and neither is moved to the other
        changes.update({name: value for name, value in wanted.items() if getattr(kept, name) != value})
    elif lead.cost_state == cost_words.FAILED and kept.cost_usd_30d is None and kept.cost_state != cost_words.FAILED:
        changes["cost_state"] = cost_words.FAILED  # a case that never had a figure says that it could not be read just now
    return replace(kept, **changes) if changes else None


def refresh(store, ranked: Sequence[Lead]) -> int:
    """Gives each case that has an open request, and that a lead of this Watch is about, what the lead says now (_brought_up). Only a request that is still open is touched: the cost that a change
    is checked against is never moved after the person has approved it. Returns how many cases changed. A store that fails leaves the rest as it is."""
    try:
        waiting = {plan.case_id for plan in store.plans_open() if plan.state == "open"}
    except StoreError:
        return 0
    changed = 0
    for lead in ranked:
        case_id = f"k{lead.lead_id}"
        if case_id not in waiting:
            continue
        try:
            if store.case_update(case_id, lambda kept, lead=lead: _brought_up(kept, lead)):
                changed += 1
        except StoreError:
            continue
    return changed


def held(history: History, case: CaseRecord, why: str = "") -> str:
    """Says in the History that a finding was held back, because it cannot say what to look at (`why` empty) or by a rule of cases/brief.py held_reason (`why` is its reason): its case stays, no request
    is made. Returns the words that it said."""
    reason = HELD_BACK.get(why, NOTHING_TO_SAY)
    history.emit("case.held", caseId=case.case_id, detector=case.detector, resourceType=clean_text(case.resource_type, 120), resourceName=clean_text(case.resource_name, 120), reason=reason)
    return reason


def take_back(ex, history: History) -> Counter:
    """Takes back the open requests of the findings that cannot say what to look at, that the rules hold back or that were made under rules that have changed, when nobody has answered them
    (Approvals.hold_back_empty), says each in the History and returns how many there were of each reason, in the words that the History says."""
    return Counter(held(history, case, brief.taken_back(case)) for _, case in ex.approvals.hold_back_empty())
