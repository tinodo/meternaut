"""Azure Advisor's cost recommendations as cases (docs/proposals/22-advisor-first-class.md): made by code from Advisor's own typed values, and never judged by a model.

Advisor lists the same purchase more than once, for each term and each look-back. Those variants are alternatives of one decision, so they are one case, one request and one figure: the smallest.
A decision about a whole subscription is one case; a recommendation about one resource is a case for that resource, or a row of the case that an older check of Meternaut or the investigation
made for it. Commitments of one subscription that Advisor offers in more than one way are alternatives too, and only the larger is counted. Nothing here changes Azure.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from collections.abc import Collection
from dataclasses import replace

from . import costs as cost_words
from . import upkeep
from .brief import ADVISOR_KEY as KEY
from .brief import ADVISOR_ROWS as ROWS
from .brief import advisor_says, says_nothing
from .detectors import ADVISOR, DETECTORS, Context, Lead, ident
from .memory_store import parse, stamp
from .models import ADVICE_QUIET_DAYS, INVESTIGATION, CaseRecord, StoreError
from .roles import clean_text

CASES_READ = 200
ASKS = ("needs_human", "error", "dropped", "proposed")  # no person has answered the case: a Watch asks about it again (an earlier version let the two AIs judge Advisor's leads)
ADVICE_NONE = {"problem": "Azure Advisor has a cost recommendation", "solution": "Azure Advisor gave no words for it: its figures and details are listed here"}


def group_key(lead: Lead) -> str:
    """What one case stands for. For a whole subscription: the subscription, type, sub-category, size or product, region and scope, which Advisor repeats for each term and look-back, so the variants
    share it. The quantity is not in it: the engine recommends the quantity that saves most for each look-back (Learn), so it differs between variants, and the case must not change when it does.
    A recommendation with no term or no look-back is its own decision, never merged by a guess. For anything else: the resource."""
    item = lead.advisor
    if cost_words.scope_of(lead.resource_id).kind != "subscription":
        return lead.resource_id.lower()
    if item["term"] and item["lookback"] is not None:
        return "|".join((lead.subscription_id, item["type"], item["sub"], item["sku"], item["region"], item["scope"]))
    return f"{lead.subscription_id}|{lead.lead_id}"


def resources(leads: list[Lead]) -> set[str]:
    """The resources that Advisor has a recommendation of their own about: the older checks leave their lead for such a resource to its case, which holds what Advisor says."""
    return {lead.resource_id.lower() for lead in leads if lead.detector == ADVISOR and group_key(lead) == lead.resource_id.lower()}


def digest(leads: list[Lead], dollars: bool) -> dict:
    """What a decision says, as typed values: its variants (the first ROWS, the smallest figure first), the smallest and the largest of them in dollars a year, and `usd`, the one figure that is
    counted. The variants of a purchase are alternatives, so the counted figure is the smallest; recommendations about one resource overlap, so it is the largest. A variant in another currency, or
    with no figure, is counted and not added; one that names no currency is read as dollars when the cost lines of its subscription are (`dollars`)."""
    items = sorted((lead.advisor for lead in leads), key=lambda item: (item["annual"] is None, item["annual"] or 0.0, item["term"], item["lookback"] or 0, item["sku"]))
    counted = [item["annual"] is not None and (item["currency"] == "USD" or (not item["currency"] and dollars)) for item in items]
    figures = [item["annual"] for item, yes in zip(items, counted) if yes]
    low, high = (min(figures), max(figures)) if figures else (0.0, 0.0)
    return {"type": items[0]["type"], "sub": items[0]["sub"], "n": len(items), "added": sum(counted), "skipped": len(items) - sum(counted),
            "currencies": sorted({item["currency"] for item in items if item["currency"] not in ("", "USD")}), "low": round(low, 2), "high": round(high, 2),
            "usd": round(low if any(item["term"] for item in items) else high, 2), "alt": "",
            "rows": [[item["sku"], item["qty"], item["region"], item["term"], item["annual"], "USD" if yes else item["currency"], item["lookback"], item["scope"]]
                     for item, yes in zip(items[:ROWS], counted)], "more": max(0, len(items) - ROWS)}


def _alternatives(groups: dict[str, list[Lead]], decisions: dict[str, dict]) -> None:
    """Among the commitments of one subscription (decisions whose variants have a term) only one way to buy is counted. A product that Advisor offers in another scope counts once, by its larger
    figure, and a kind of commitment (Advisor's sub-category) is an alternative to another kind, because Advisor's fields do not say which spend each covers: the kind whose products add up
    to most is counted. The others keep their figures, are not added (`usd` 0), and say what is counted instead (`alt`)."""
    mine: dict[str, list[str]] = defaultdict(list)
    for key, said in decisions.items():
        if any(row[3] for row in said["rows"]):
            mine[groups[key][0].subscription_id].append(key)
    for keys in mine.values():
        best: dict[tuple, str] = {}
        for key in sorted(keys):
            said = decisions[key]
            product = (said["type"], said["rows"][0][0], said["rows"][0][2])
            if product not in best or said["low"] > decisions[best[product]]["low"]:
                best[product] = key
        total: dict[str, float] = defaultdict(float)
        for key in best.values():
            total[decisions[key]["sub"]] += decisions[key]["low"]
        winner = max(total, key=lambda kind: (total[kind], kind))
        for key in keys:
            if key not in best.values() or decisions[key]["sub"] != winner:
                decisions[key].update(usd=0.0, alt=re.sub(r"(?<=[a-z])(?=[A-Z])", " ", winner).lower() or "another kind")


def _asks_again(old: CaseRecord, now: dt.datetime, recheck_days: int) -> bool:
    """Whether a Watch asks about a case again: nobody has answered it, or the answer of a person (held ADVICE_QUIET_DAYS) or the end of an unanswered request (held the days that the AI cases wait)
    is older than the time that it holds the question back."""
    held = {"declined": ADVICE_QUIET_DAYS, "acknowledged": ADVICE_QUIET_DAYS, "expired": recheck_days}.get(old.status)
    return old.status in ASKS or (held is not None and bool(old.updated_at) and now - parse(old.updated_at) >= dt.timedelta(days=held))


def _mate(store, key: str) -> CaseRecord | None:
    """The case that an older check or the investigation made for the resource, when it still stands for a finding (a case that was dropped or ended in an error does not)."""
    for name in (*(d.name for d in DETECTORS), INVESTIGATION):
        found = store.case_get(f"k{ident(name, key)}")
        if found is not None and found.status not in ("dropped", "error"):
            return found
    return None


def _case(s, key: str, leads: list[Lead], said: dict, others: set[str], holds: list[str] | None, listed: set[str]) -> int:
    """Makes or brings up to date the case for one decision and asks about it. Returns 1 when the case is new or is asked about again. A case that an older check or an AI made for the resource keeps
    its own flow, its status and its time: it only gets what Advisor says, in its facts."""
    ex, h = s.extras, s.history
    lead, now = leads[0], s.clock()
    single = key == lead.resource_id.lower()
    mate = _mate(ex.store, key) if single else None
    if mate is not None:
        listed.add(mate.case_id)
        if mate.facts.get(KEY) != said:
            ex.store.case_update(mate.case_id, lambda kept: replace(kept, facts={**kept.facts, KEY: said}))
        return 0
    case_id = f"k{ident(ADVISOR, key)}"
    listed.add(case_id)
    old = ex.store.case_get(case_id)
    if single and others:
        said["also"] = sorted(others)  # the older checks found the same resource, and their lead is left to this case
    if old is not None and not _asks_again(old, now, ex.settings.recheck_days):
        if old.facts.get(KEY) != said:  # an answer, or a request that is running, stays as it is: only what Advisor says is brought up to date
            ex.store.case_update(case_id, lambda kept: replace(kept, facts={**kept.facts, KEY: said}))
        return 0
    fresh = old is None or old.status != "needs_human"
    impact = next((word for word in ("high", "medium", "low") if any(item.facts.get("impact") == word for item in leads)), "other")
    changes: dict = {"status": "needs_human", "updated_at": stamp(now) if fresh else old.updated_at, "runs_seen": old.runs_seen + 1 if old else 1,
                     "facts": {**(old.facts if old else {"category": "cost", "impact": impact}), KEY: said}, "run_id": h.run_id, "resource_name": clean_text(lead.name, 120),
                     "subscription_name": lead.subscription_name, "advice": next((i.advice for i in leads if i.advice), ADVICE_NONE if advisor_says(said) else {}),
                     **upkeep.cost_fields(lead, old)}
    record = replace(old, **changes) if old else CaseRecord(
        case_id=case_id, resource_id=lead.resource_id, resource_type=clean_text(lead.resource_type, 120), resource_group=clean_text(lead.resource_group, 90),
        subscription_id=lead.subscription_id, detector=ADVISOR, recommendation="change", first_seen_at=stamp(now), **changes)
    ex.store.case_put(record)
    if not fresh and says_nothing(record):
        return 0  # it was said when the case was made that it has nothing to say, and it is not said again at each Watch
    if fresh:
        h.emit("case.started", caseId=case_id, leadId=lead.lead_id)
        h.emit("case.result", caseId=case_id, leadId=lead.lead_id, detector=record.detector, resourceName=clean_text(record.resource_name, 120), resourceType=record.resource_type,
               resourceGroup=clean_text(record.resource_group, 90), costUsd30d=record.cost_usd_30d, status="needs_human", recommendation="change", confidence=None,
               monthlySavingUsd=round(said["usd"] / 12, 2) if said["usd"] > 0 else None, summary=f"Azure Advisor: {said['n']} recommendation{'' if said['n'] == 1 else 's'} in one decision, "
               + ("an alternative, none counted" if said["alt"] else f"{said['usd']:.2f} a year counted"), objections=[], guards=[])
    upkeep.ask(ex, h, record, lead, holds)
    return int(fresh)


def _close(ex, listed: set[str], read: set[str], replaced: set[str], now: dt.datetime) -> tuple[int, int]:
    """Closes the Advisor cases that no recommendation stands for any more, in the subscriptions whose list Advisor gave in this Watch (`read`; a list that could not be read says nothing about what
    is on it): a decision that Advisor does not list now (bought, or recomputed into another), and the one case that an earlier version made for a whole subscription, which the decisions of the
    subscriptions in `replaced` replace. A request that a person has answered, or put off, stays theirs. Returns how many of the second and of the first were closed."""
    plans = {plan.case_id: plan for plan in ex.store.plans_open() if plan.state == "open"}
    earlier = gone = 0
    for case in ex.store.cases_recent(CASES_READ):
        if case.detector != ADVISOR or case.subscription_id not in read or case.case_id in listed or case.status not in ("proposed", "needs_human"):
            continue
        first = KEY not in case.facts and cost_words.scope_of(case.resource_id).kind == "subscription"
        plan = ex.store.plan_get(plans[case.case_id].plan_id) if case.case_id in plans else None
        if (first and case.subscription_id not in replaced) or (plan is not None and (plan.state != "open" or ex.store.decisions_of_plan(plan.plan_id))):
            continue
        if plan is not None:
            ex.store.plan_put(replace(plan, state="expired", expires_at=stamp(now), preconditions={**(plan.preconditions or {}), "takenBack": "advisor" if first else "delisted"}))
        ex.store.case_update(case.case_id, lambda kept: replace(kept, status="expired"))
        earlier, gone = earlier + first, gone + (not first)
    return earlier, gone


def make(s, ranked: list[Lead], contexts: dict[str, Context], say, holds: list[str] | None, read: Collection[str] = ()) -> int:
    """The step of a Watch that makes the case of every decision of Advisor, whether or not the investigation ran, and asks a person about each (upkeep.ask). A case that a person has answered, or
    whose request is open, only has what Advisor says brought up to date. `read` holds the subscriptions whose list Advisor gave in this Watch: the cases of theirs that it does not list now are
    closed. Says what was counted and not added up. Returns the cases that were made or asked about again. A store that fails is a note."""
    groups: dict[str, list[Lead]] = defaultdict(list)
    others: dict[str, set[str]] = defaultdict(set)
    for lead in ranked:
        if lead.detector == ADVISOR:
            groups[group_key(lead)].append(lead)
        else:
            others[lead.resource_id.lower()].add(lead.detector)
    made = skipped = 0
    currencies: set[str] = set()
    listed: set[str] = set()
    broken = False
    decisions = {key: digest(leads, (contexts.get(leads[0].subscription_id) or Context()).currency == "USD") for key, leads in groups.items()}
    _alternatives(groups, decisions)
    for key, leads in groups.items():
        said = decisions[key]
        skipped += said["skipped"]
        currencies.update(said["currencies"])
        try:
            made += _case(s, key, leads, said, others.get(key, set()), holds, listed)
        except StoreError as error:
            broken = True
            say(f"the case of {len(leads)} Advisor recommendation{'' if len(leads) == 1 else 's'} could not be kept in the store: {clean_text(s.redact(error), 200)}")
    try:
        earlier, gone = _close(s.extras, listed, set(read), {leads[0].subscription_id for leads in groups.values()}, s.clock()) if not broken else (0, 0)
        if earlier:
            say(f"{earlier} earlier request{'s' if earlier != 1 else ''} about whole subscriptions {'were' if earlier != 1 else 'was'} closed: Advisor's recommendations have a request for each decision now")
        if gone:
            say(f"{gone} Advisor request{'s' if gone != 1 else ''} {'were' if gone != 1 else 'was'} closed: Advisor does not list {'them' if gone != 1 else 'it'} any more")
    except StoreError as error:
        say(f"the requests of recommendations that Advisor does not list any more could not be closed: {clean_text(s.redact(error), 200)}")
    if skipped:
        say(f"{skipped} Advisor recommendation{'' if skipped == 1 else 's'} {'was' if skipped == 1 else 'were'} counted and not added up: no figure in dollars"
            + (f" ({', '.join(sorted(currencies))})" if currencies else "") + ", so no saving is stated for them")
    return made
