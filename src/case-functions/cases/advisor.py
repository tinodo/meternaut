"""Azure Advisor's cost recommendations as cases (docs/proposals/22-advisor-first-class.md): made by code from Advisor's own typed values, and never judged by a model.

A recommendation about a whole subscription (a reservation, a savings plan) is one row of one case for each subscription, type and sub-category, with the sum and the first rows; a recommendation
about one resource is one case for that resource. When an older check of Meternaut or the investigation has a case for that resource, that case holds what Advisor says and no second case is made.
Nothing here changes Azure. It reads Advisor's list that the Watch read, and writes the records of the app.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import replace

from . import costs as cost_words
from . import upkeep
from .detectors import ADVISOR, DETECTORS, Context, Lead, ident
from .memory_store import parse, stamp
from .models import ADVICE_QUIET_DAYS, INVESTIGATION, CaseRecord, StoreError
from .roles import clean_text

KEY = "advisor"  # the key, in the facts of a case, of what Advisor says (cases/brief.py reads it)
ROWS = 12  # the rows of one case that a person is shown; the others are counted, with their sum
ASKS = ("needs_human", "error")  # the statuses of a case that no person has answered and that has no request open: a Watch asks about it again


def group_key(lead: Lead) -> str:
    """What one case stands for: the subscription, the type and the sub-category of a recommendation about a whole subscription, else the resource."""
    if cost_words.scope_of(lead.resource_id).kind == "subscription":
        return f"{lead.subscription_id}|{lead.advisor.get('type', '')}|{lead.advisor.get('sub', '')}"
    return lead.resource_id.lower()


def resources(leads: list[Lead]) -> set[str]:
    """The resources that Advisor has a recommendation of their own about (the older checks leave a lead for such a resource to its case, which holds what Advisor says)."""
    return {lead.resource_id.lower() for lead in leads if lead.detector == ADVISOR and group_key(lead) == lead.resource_id.lower()}


def digest(leads: list[Lead], dollars: bool) -> dict:
    """What a group of recommendations says, as typed values for a person to read: how many there are, what their yearly savings add up to in dollars, the first ROWS of them, the largest first,
    and how many more there are with their sum. A recommendation in another currency, or with no figure, is counted and not added; one that names no currency is read as dollars when the cost
    lines of its subscription are in dollars (`dollars`)."""
    items = sorted((lead.advisor for lead in leads), key=lambda item: (-(item["annual"] or 0.0), item["sku"]))
    counted = [item["annual"] is not None and (item["currency"] == "USD" or (not item["currency"] and dollars)) for item in items]
    return {"type": items[0]["type"], "sub": items[0]["sub"], "n": len(items), "added": sum(counted), "skipped": len(items) - sum(counted),
            "currencies": sorted({item["currency"] for item in items if item["currency"] not in ("", "USD")}),
            "usd": round(sum(item["annual"] for item, yes in zip(items, counted) if yes), 2),
            "rows": [[item["sku"], item["qty"], item["region"], item["term"], item["annual"], "USD" if yes else item["currency"], item["lookback"], item["scope"]]
                     for item, yes in zip(items[:ROWS], counted)],
            "more": max(0, len(items) - ROWS), "moreUsd": round(sum(item["annual"] for item, yes in zip(items[ROWS:], counted[ROWS:]) if yes), 2)}


def _asks_again(old: CaseRecord, now: dt.datetime, recheck_days: int) -> bool:
    """Whether a Watch asks about a case again: nobody has answered it, or the answer of a person (held for ADVICE_QUIET_DAYS) or the end of an unanswered request (held for the days that the AI cases
    wait) is older than the time that it holds the question back."""
    held = {"declined": ADVICE_QUIET_DAYS, "acknowledged": ADVICE_QUIET_DAYS, "expired": recheck_days}.get(old.status)
    return old.status in ASKS or (held is not None and bool(old.updated_at) and now - parse(old.updated_at) >= dt.timedelta(days=held))


def _mate(store, key: str) -> CaseRecord | None:
    """The case that an older check of Meternaut or the investigation made for the resource, when it still stands for a finding (a case that was dropped or ended in an error does not)."""
    for name in (*(d.name for d in DETECTORS), INVESTIGATION):
        found = store.case_get(f"k{ident(name, key)}")
        if found is not None:
            return found if found.status not in ("dropped", "error") else None
    return None


def _case(s, key: str, leads: list[Lead], said: dict, others: set[str], holds: list[str] | None) -> int:
    ex, h = s.extras, s.history
    lead, now = leads[0], s.clock()
    single = key == lead.resource_id.lower()
    mate = _mate(ex.store, key) if single else None
    case_id = mate.case_id if mate is not None else f"k{ident(ADVISOR, key)}"
    old = mate or ex.store.case_get(case_id)
    if single and mate is None and others:
        said["also"] = sorted(others)  # the older checks of Meternaut found the same resource, and their lead is left to this case
    if old is not None and not _asks_again(old, now, ex.settings.recheck_days):
        if old.facts.get(KEY) != said:  # an answer, or a request that is running, stays as it is: only what Advisor says is brought up to date
            ex.store.case_update(case_id, lambda kept: replace(kept, facts={**kept.facts, KEY: said}))
        return 0
    changes: dict = {"status": "needs_human", "updated_at": stamp(now), "runs_seen": old.runs_seen + 1 if old else 1, "facts": {**(old.facts if old else {"category": "cost"}), KEY: said}}
    if mate is None:
        changes.update(run_id=h.run_id, resource_name=clean_text(lead.name, 120), subscription_name=lead.subscription_name, advice=lead.advice, **upkeep.cost_fields(lead, old))
    elif not mate.advice:
        changes["advice"] = lead.advice
    record = replace(old, **changes) if old else CaseRecord(
        case_id=case_id, resource_id=lead.resource_id, resource_type=clean_text(lead.resource_type, 120), resource_group=clean_text(lead.resource_group, 90),
        subscription_id=lead.subscription_id, detector=ADVISOR, recommendation="change", first_seen_at=stamp(now), **{"resource_name": "", "run_id": "", **changes})
    ex.store.case_put(record)
    h.emit("case.started", caseId=case_id, leadId=lead.lead_id)
    h.emit("case.result", caseId=case_id, leadId=lead.lead_id, detector=record.detector, resourceName=clean_text(record.resource_name, 120), resourceType=record.resource_type,
           resourceGroup=clean_text(record.resource_group, 90), costUsd30d=record.cost_usd_30d, status="needs_human", recommendation="change", confidence=None,
           monthlySavingUsd=round(said["usd"] / 12, 2) if said["usd"] > 0 else None, summary=f"Azure Advisor: {said['n']} recommendation{'' if said['n'] == 1 else 's'}, {said['skipped']} not added up",
           objections=[], guards=[])
    upkeep.ask(ex, h, record, lead, holds)
    return 1


def make(s, ranked: list[Lead], contexts: dict[str, Context], say, holds: list[str] | None) -> int:
    """The step of a Watch that makes the case of every recommendation of Advisor, whether or not the investigation ran, and asks a person about each (upkeep.ask). A case that a person has
    answered, or whose request is open, only has what Advisor says brought up to date. Says in the History how many recommendations were counted and not added. Returns the cases that it
    made or opened again. It never raises: a store that fails is a note."""
    if s.extras is None:
        return 0
    groups: dict[str, list[Lead]] = defaultdict(list)
    others: dict[str, set[str]] = defaultdict(set)
    for lead in ranked:
        if lead.detector == ADVISOR:
            groups[group_key(lead)].append(lead)
        else:
            others[lead.resource_id.lower()].add(lead.detector)
    made = skipped = 0
    currencies: set[str] = set()
    for key, leads in groups.items():
        context = contexts.get(leads[0].subscription_id)
        said = digest(leads, context is not None and context.currency == "USD")
        skipped += said["skipped"]
        currencies.update(said["currencies"])
        try:
            made += _case(s, key, leads, said, others.get(key, set()), holds)
        except StoreError as error:
            say(f"the case of {len(leads)} Advisor recommendation{'' if len(leads) == 1 else 's'} could not be kept in the store: {clean_text(s.redact(error), 200)}")
    if skipped:
        say(f"{skipped} Advisor recommendation{'' if skipped == 1 else 's'} {'was' if skipped == 1 else 'were'} counted and not added up: no figure in dollars"
            + (f" ({', '.join(sorted(currencies))})" if currencies else "") + ", so no saving is stated for them")
    return made


