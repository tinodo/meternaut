"""One run of the Watch: find leads, let the investigation look for waste by itself, take the leads that are left through the two model roles, apply the guards,
write the History.

Nothing here changes Azure. The limits of docs/proposals/02-first-cases.md are applied here: the cases per run, the tokens per run and per
call, the deadline, the retries (in http.py) and the refusals of the model service. The investigation (investigate.py) has a budget of its own, and the time that it
takes is not taken from the deadline of the cases that follow it.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import time
import uuid
from collections import Counter
from dataclasses import dataclass, replace
from typing import Callable, Mapping, Sequence

from . import config as cfg
from . import costs as cost_words
from . import decide, detectors, evidence, guards, investigate, learning, roles, upkeep, usage, wiring
from . import harness as harness_module
from . import scope as scope_mod
from .approvals import HELD_BACK, NOTHING_TO_SAY, is_fixture
from .arm import Arm, scopes_of
from .brief import says_nothing
from .detectors import DETECTOR_NAMES, Context, Estate, Lead
from .events import History
from .evidence import EvidenceError
from .foundry import Foundry
from .http import Client, HttpError, allowed_calls, default_transport
from .identity import Identity
from .memory_store import parse, stamp
from .modelcalls import ModelError, Models
from .models import GROUP_FACT, CaseRecord, RunRecord, StoreError
from .redact import Redactor
from .roles import RoleError, clean_text

MAX_LEAD_EVENTS = 50
PROMPT_TOKEN_RESERVE = 2000
# What the reading of the subscriptions may use of the run's deadline. The rest is for the cases that follow (the Detective and the Skeptic) and for the checks around them; the
# investigation has a time of its own, which is not taken from the deadline. A subscription that the share has no time for is not read, and the History says which.
READ_SHARE = 0.6
# A subscription that was started inside the share may finish its own reads (Advisor, locks, cost lines) this much later; a call after that is refused by the client, as after the deadline.
READ_GRACE = 0.1
SCOPES_SHOWN = 5  # the subscriptions that run.started names, at eight characters each; it also carries their count
COST_DAYS = 30  # the closed days of cost_usd_30d, and of the series that a case with an open plan carries (CaseRecord.cost_series)
COST_IDS = 50  # the resource ids that one Cost Management query asks about
USE_MAX_RESOURCES = 30  # the resources whose use one Watch reads (one read of Azure Monitor for each of their metrics): the others wait for the next Watch
USE_MIN_SECONDS = 30  # the use of a resource is not read when the run has less time than this left: one read of Azure Monitor may take that long
LOG = logging.getLogger("meternaut.run")


@dataclass
class Services:
    settings: cfg.Settings
    client: Client
    arm: Arm
    models: Models
    history: History
    redact: Redactor
    clock: Callable[[], dt.datetime]
    monotonic: Callable[[], float]
    extras: "wiring.Extras | None" = None
    foundry: "Foundry | None" = None
    # What surrounds the agents (cases/harness.py). The client of the Foundry project that run_watch makes always has one; a test that plays the agents gives none, or its own.
    harness: "harness_module.Harness | None" = None


@dataclass
class Summary:
    ok: bool = True
    leads: int = 0
    cases: int = 0
    proposed: int = 0
    needs_human: int = 0
    dropped: int = 0
    errors: int = 0
    tokens: int = 0
    seconds: int = 0
    held: int = 0  # the findings held back because they cannot say what to look at, or because an automation manages the resource (cases/upkeep.py)


class CaseEnded(Exception):
    """A case that cannot go on; the text says why."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _figure(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _cases(number: int) -> str:
    return "1 case was" if number == 1 else f"{number} cases were"


# The daily timer fires at the same minute every day, so a run is a few seconds or minutes short of whole days after the last one: this much slack keeps "seven days" from becoming eight.
TIMER_SLACK = dt.timedelta(hours=1)


def investigation_wait(s: Services, trigger: str) -> str | None:
    """None when the investigation is due; else the plain reason why it waits. A run that a person starts (any trigger but the daily timer) always investigates. The daily timer investigates when
    INVESTIGATE_EVERY_DAYS have passed since the last run that investigated, because a run costs about half a US dollar and the owner's standing limit of 5 a day and 25 a month for each caller is
    shared with the evaluations, the red team and the runs that people start.
    A store that cannot be read, or a time that cannot be read, means that the investigation waits: nothing is spent on a guess."""
    if trigger != "timer" or s.extras is None:
        return None
    every = s.settings.investigate_every_days
    try:
        runs = s.extras.store.runs_recent(60)
    except StoreError:
        return "the earlier runs could not be read, so the cost of another investigation was not weighed"
    now = s.clock()
    # A run that is dated after now (a clock that went back, or a record that somebody wrote) counts for nothing: it would hold the timer off for days that have not come.
    last = max((parsed for parsed in (_when(run.started_at) for run in runs if run.investigated) if parsed is not None and parsed <= now), default=None)
    if last is None:
        return None
    waited = now - last
    if waited >= dt.timedelta(days=every) - TIMER_SLACK:
        return None
    days = waited.days
    return f"the last investigation ran {days} day{'' if days == 1 else 's'} ago, and the timer investigates every {every} days (INVESTIGATE_EVERY_DAYS); a run that a person starts does it at once"


def _when(value: object) -> dt.datetime | None:
    try:
        return parse(str(value))
    except ValueError:
        return None


def work_case(s: Services, number: int, lead: Lead, context: Context, tokens_before: int, held: list[str] | None = None) -> tuple[str, int]:
    """One case, from the evidence to the result. Returns its status and the tokens that it used. `held` collects the words of the History for each case whose request was not made because the finding
    cannot say what to look at, or because a rule holds it back (cases/upkeep.py, cases/brief.py held_reason): the Watch counts them."""
    h, st = s.history, s.settings
    case_id = f"{h.run_id[:8]}-c{number}"
    used = 0
    h.emit("case.started", caseId=case_id, leadId=lead.lead_id)
    identity = {"caseId": case_id, "leadId": lead.lead_id, "detector": lead.detector, "resourceName": clean_text(lead.name, 120),
                "resourceType": clean_text(lead.resource_type, 120), "resourceGroup": clean_text(lead.resource_group, 90), "costUsd30d": lead.cost_usd_30d}
    steps: list[dict] = []
    models: dict[str, str | None] = {"detective": st.model_detective, "skeptic": None}

    def save(status: str, recommendation: str | None, confidence: float | None, saving: float | None, summary: str, objections: list[str], flags_on: list[str],
             facts: dict, skeptic: str = "none") -> None:
        """The case goes to the store, when there is one, and a plan is made when a person could approve a change for it. A store that fails never stops the run."""
        ex = s.extras
        if ex is None:
            return
        now = stamp(s.clock())
        try:
            old = ex.store.case_get(f"k{lead.lead_id}")
            record = CaseRecord(
                case_id=f"k{lead.lead_id}", resource_id=lead.resource_id, resource_name=clean_text(lead.name, 120), resource_type=clean_text(lead.resource_type, 120),
                resource_group=clean_text(lead.resource_group, 90), subscription_id=lead.subscription_id, detector=lead.detector, run_id=h.run_id, status=status,
                recommendation=recommendation, confidence=confidence, saving_usd_month=saving, summary=clean_text(summary, 600),
                objections=tuple(clean_text(o, 300) for o in objections), guards=tuple(flags_on), models=dict(models), steps=tuple(steps), facts=facts,
                first_seen_at=old.first_seen_at if old and old.first_seen_at else now, updated_at=now, runs_seen=(old.runs_seen + 1) if old else 1, learned={"skeptic": skeptic},
                subscription_name=lead.subscription_name or (old.subscription_name if old else ""), advice=lead.advice or (old.advice if old else {}), **upkeep.cost_fields(lead, old))
            ex.store.case_put(record)
            if status in ("proposed", "needs_human"):
                plan = ex.approvals.plan_for(record, lead, ex.approvers())
                if plan is not None:
                    record = learning.remember(ex.store, record, plan)  # how past requests like this were answered: the one line of the brief
                    h.emit("plan.created", planId=plan.plan_id, caseKey=record.case_id, family=plan.family, approvers=len(plan.approvers))
                    ex.on_plan(plan, ex.store.case_get(record.case_id) or record)
                else:
                    why = ex.approvals.held_why(record)  # the rules that hold a deletion back whichever detector made the case (cases/brief.py held_reason)
                    if (why or says_nothing(record)) and held is not None:
                        held.append(upkeep.held(h, record, why))
        except (StoreError, ValueError) as error:
            h.emit("run.note", note=clean_text(s.redact(f"the case could not be kept in the store: {error}"), 300))

    def ended(note: str) -> tuple[str, int]:
        h.emit("case.result", **identity, status="error", recommendation=None, confidence=None, monthlySavingUsd=None, summary=note, objections=[], guards=[])
        save("error", None, None, None, note, [], [], {})
        return "error", used

    def step(name: str, model: str | None, started: float, ok: bool, note: str | None = None, chat_tokens: tuple[int, int] | None = None) -> None:
        ms = int((s.monotonic() - started) * 1000)
        steps.append({"step": name, "model": model, "promptTokens": chat_tokens[0] if chat_tokens else None,
                      "completionTokens": chat_tokens[1] if chat_tokens else None, "ms": ms, "ok": ok, "note": note})
        h.emit("case.step", caseId=case_id, step=name, model=model, promptTokens=chat_tokens[0] if chat_tokens else None,
               completionTokens=chat_tokens[1] if chat_tokens else None, ms=ms, ok=ok, note=note)

    def role(name: str, model: str, system: str, user: str, parse: Callable[[str], object]):
        nonlocal used
        started = s.monotonic()
        if tokens_before + used + st.max_completion_tokens + PROMPT_TOKEN_RESERVE > st.max_tokens_per_run:
            step(name, model, started, False, "the token budget of the run was reached")
            raise CaseEnded("the token budget of the run was reached")
        chat = None
        try:
            chat = s.models.chat(model, system, user, st.max_completion_tokens)
            used += chat.total_tokens
            answer = parse(chat.text)
        except (ModelError, RoleError) as error:
            note = clean_text(s.redact(error), 200)
            step(name, model, started, False, note, (chat.prompt_tokens, chat.completion_tokens) if chat else None)
            raise CaseEnded(note) from error
        step(name, model, started, True, None, (chat.prompt_tokens, chat.completion_tokens))
        return answer

    started = s.monotonic()
    try:
        scope_locks: list[str] | None = []
        for scope in scopes_of(lead.resource_id):
            scope_locks += s.arm.locks_at(lead.subscription_id, scope)
    except HttpError:
        scope_locks = None
    fixture = s.extras is not None and is_fixture(lead, wiring.approval_settings(s.extras.settings))
    flags = guards.evaluate(lead, context, scope_locks, fixture=fixture)
    try:
        case = evidence.case_dto(number, evidence.model_lead(lead, fixture), flags)
    except EvidenceError as error:
        step("evidence", None, started, False, clean_text(error, 200))
        return ended(clean_text(error, 200))
    step("evidence", None, started, True)
    step("guards", None, s.monotonic(), True, ", ".join(flags.names) or "none")
    try:
        detective = role("detective", st.model_detective, roles.DETECTIVE_SYSTEM, roles.detective_user(case), roles.parse_detective)
        skeptic = None
        if detective.recommendation != "keep":
            skeptic = role("skeptic", st.model_skeptic, roles.SKEPTIC_SYSTEM, roles.skeptic_user(case, detective), roles.parse_skeptic)
    except CaseEnded as error:
        return ended(str(error))
    outcome = decide.decide(lead, flags, detective, skeptic)
    h.emit("case.result", **identity, status=outcome.status, recommendation=outcome.recommendation, confidence=outcome.confidence,
           monthlySavingUsd=_figure(outcome.monthly_saving_usd), summary=outcome.summary, objections=list(outcome.objections), guards=outcome.guards)
    models["skeptic"] = st.model_skeptic if skeptic else None
    save(outcome.status, outcome.recommendation, outcome.confidence, _figure(outcome.monthly_saving_usd), outcome.summary, list(outcome.objections), outcome.guards,
         case["facts"], skeptic.verdict if skeptic else "none")
    return outcome.status, used


def _recently_judged(s: Services, lead: Lead) -> bool:
    """A lead whose case was judged within the last days (and did not end in an error or a failed change) is not taken up again: the slot goes to a lead that was not judged."""
    ex = s.extras
    if ex is None:
        return False
    try:
        old = ex.store.case_get(f"k{lead.lead_id}")
    except StoreError:
        return False
    if old is None or old.status in ("error", "failed") or not old.updated_at:
        return False
    age = s.clock() - dt.datetime.strptime(old.updated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    return age < dt.timedelta(days=ex.settings.recheck_days)


def _currency_notes(contexts: Mapping[str, Context]) -> list[str]:
    """What the cost lines said about their currency: a note for each currency that is not US dollars, naming the subscription when it is one and counting them when they are more."""
    by_currency: dict[str, list[str]] = {}
    for subscription, context in contexts.items():
        if context.currency not in (None, "USD"):
            by_currency.setdefault(str(context.currency), []).append(subscription)
    notes = []
    for currency, found in by_currency.items():
        if len(found) == 1:
            notes.append(f"{found[0][:8]}: the cost lines are in {currency}, so no figure is shown in US dollars")
        else:
            notes.append(f"the cost lines of {len(found)} subscriptions ({detectors.some(found)}) are in {currency}, so no figure is shown in US dollars for them")
    return notes


def _unread_note(estate: Estate, deadline_seconds: int) -> str:
    """Which subscriptions were not read, and why: a count and the first few ids, never the whole list."""
    count = len(estate.unread)
    what = f"{count} subscription{' was' if count == 1 else 's were'} not read ({detectors.some(estate.unread)})"
    if estate.stopped == "identity":
        return f"{what}: {estate.reason}"
    return f"{what}: the time for reading them ({int(READ_SHARE * deadline_seconds)} of the {deadline_seconds} seconds of the run) was used up"


def _members(case: CaseRecord) -> list[str]:
    """The lower-case ids of what a case stands for: its resource, or the ones that a group case kept (none when it kept fewer than it covers)."""
    group = case.facts.get(GROUP_FACT) if isinstance(case.facts, dict) else None
    if not isinstance(group, dict):
        return [case.resource_id.lower()]
    ids = group.get("resourceIds")
    return [i.lower() for i in ids] if isinstance(ids, list) and len(ids) == group.get("count") and all(isinstance(i, str) for i in ids) else []


def _subscription(resource_id: str) -> str:
    return resource_id.split("/")[2] if resource_id.startswith("/subscriptions/") else ""


def _read_today(case: CaseRecord, last: dt.date) -> bool:
    """Whether the daily cost of a case was read for yesterday already: it holds the thirty days that end yesterday, or it was read for yesterday and Azure has no cost line for it (a series of
    nothing is not kept: cost_state says none, and the end says on which day that was found)."""
    if case.cost_series_end != last.isoformat():
        return False
    return len(case.cost_series or ()) == COST_DAYS or (case.cost_series is None and case.cost_state == cost_words.NONE)


def _with_series(kept: CaseRecord, series: list[float] | None, last: dt.date, container: bool) -> CaseRecord:
    """The case with the daily cost that was read. A series that has a day with a line is kept as it is; no line on any of the thirty days is no series (never thirty zeros): the case says that
    Azure has no cost line for it, with the day on which that was read, and a case that held no figure for its 30 days gets that figure, 0.0 as it always meant. For a subscription or a resource
    group the series is the cost of every line in it, so its sum is the cost of the 30 days, and it makes right a case whose figure was looked up by its own id."""
    if series is None:
        if (kept.cost_usd_30d or 0.0) > 0:
            return kept  # the 30 days have a cost: a day that has none is no reason to say that there is no line
        # A case that says already that Azure has no line keeps the number that it has (0.0, or none for a subscription that has no cost line at all): they mean the same.
        none = kept.cost_state == cost_words.NONE
        figure = kept.cost_usd_30d if kept.cost_usd_30d is not None or none or GROUP_FACT in (kept.facts if isinstance(kept.facts, dict) else {}) else 0.0
        return replace(kept, cost_series=None, cost_series_end=last.isoformat(), cost_state=cost_words.NONE, cost_usd_30d=figure)
    changes: dict = {"cost_series": series, "cost_series_end": last.isoformat()}
    if container and (kept.cost_state != cost_words.LINES or not kept.cost_usd_30d):
        changes.update(cost_usd_30d=round(sum(series), 2), cost_state=cost_words.LINES if sum(series) > 0 else cost_words.NONE)
    return replace(kept, **changes)


def read_cost_series(s: Services, contexts: Mapping[str, Context], say: Callable[[str], None]) -> None:
    """A step of a Watch: reads the daily cost (CaseRecord.cost_series) of each case with an open plan whose series does not end yesterday, in US dollars only, one query for each
    subscription and COST_IDS resources, and one query for a case about a whole subscription or resource group (the cost of every line in it: Arm.scope_days). A case that Azure has no cost line
    for on any of the thirty days gets no series, and says so (cost_state), never thirty zeros. A failure leaves the case as it was and is one line in the History; a limit ends the step. It
    never fails the run."""
    ex = s.extras
    if ex is None:
        return
    try:
        last = s.clock().astimezone(dt.timezone.utc).date() - dt.timedelta(days=1)
        first = last - dt.timedelta(days=COST_DAYS - 1)
        other = {sub for sub, context in contexts.items() if context.currency not in (None, "USD")}  # the Watch said already that these are not in dollars
        due: dict[str, list[str]] = {}
        wholes: dict[str, tuple[str, str]] = {}  # the case about a whole subscription or resource group -> (the subscription, the resource group or "")
        for plan in ex.store.plans_open():
            case = ex.store.case_get(plan.case_id)
            if case is None or case.case_id in due or case.case_id in wholes or _read_today(case, last):
                continue
            scope = cost_words.scope_of(case.resource_id)
            if scope.kind in ("subscription", "group") and GROUP_FACT not in (case.facts if isinstance(case.facts, dict) else {}):
                if scope.subscription not in other:
                    wholes[case.case_id] = (scope.subscription, scope.group)
                continue
            ids = _members(case)
            subs = {_subscription(i) for i in ids}
            if ids and "" not in subs and subs.isdisjoint(other):
                due[case.case_id] = ids
        by_sub: dict[str, list[str]] = {}
        for resource in sorted({i for ids in due.values() for i in ids}):
            by_sub.setdefault(_subscription(resource), []).append(resource)
        daily: dict[str, list[float]] = {}
        read: set[str] = set()
        why = ""
        stopped = False
        for sub, chunk in [(sub, ids[n:n + COST_IDS]) for sub, ids in by_sub.items() for n in range(0, len(ids), COST_IDS)]:
            try:
                rows = s.arm.cost_days(sub, first, last, where=("ResourceId", tuple(chunk)))
            except HttpError as error:
                why = why or clean_text(s.redact(error), 200)
                if error.status == 429:
                    stopped = True
                    break
                continue
            if any(code != "USD" for _, _, _, code in rows):
                why = why or "the cost lines are not in US dollars"
                continue
            for day, resource, amount, _ in rows:
                if 0 <= (day - first).days < COST_DAYS:
                    daily.setdefault(resource, [0.0] * COST_DAYS)[(day - first).days] += amount
            read.update(chunk)
        whole_series: dict[tuple[str, str], list[float] | None] = {}
        for sub, group in sorted(set(wholes.values())):
            if stopped:
                break
            try:
                rows = s.arm.scope_days(sub, first, last, group)
            except HttpError as error:
                why = why or clean_text(s.redact(error), 200)
                if error.status == 429:
                    stopped = True
                    break
                continue
            if any(code != "USD" for _, _, code in rows):
                why = why or "the cost lines are not in US dollars"
                continue
            found = [0.0] * COST_DAYS
            seen = False
            for day, amount, _ in rows:
                if 0 <= (day - first).days < COST_DAYS:
                    found[(day - first).days] += amount
                    seen = True
            whole_series[(sub, group)] = [round(value, 4) or 0.0 for value in found] if seen else None
        done = 0
        left_over: list[str] = []
        for case_id, ids in due.items():
            if not read.issuperset(ids):
                left_over.append(case_id)
                continue
            series = [round(sum(daily[i][n] for i in ids if i in daily), 4) or 0.0 for n in range(COST_DAYS)] if any(i in daily for i in ids) else None
            try:
                ex.store.case_update(case_id, lambda kept: _with_series(kept, series, last, False))  # only these fields, on the case as it is stored now
                done += 1
            except StoreError as error:
                why = why or clean_text(s.redact(error), 200)
                left_over.append(case_id)
        for case_id, key in wholes.items():
            if key not in whole_series:
                left_over.append(case_id)
                continue
            try:
                ex.store.case_update(case_id, lambda kept, series=whole_series[key]: _with_series(kept, series, last, True))
                done += 1
            except StoreError as error:
                why = why or clean_text(s.redact(error), 200)
                left_over.append(case_id)
        if left_over:
            say(f"the daily cost of {len(left_over)} open request{'' if len(left_over) == 1 else 's'} could not be read ({why}); what was read before stays")
    except Exception as error:  # noqa: BLE001 (this step never stops the run)
        say(f"the daily cost of the open requests could not be read ({clean_text(s.redact(f'{type(error).__name__}: {error}'), 200)})")


def _read_use_of(arm: Arm, resource_id: str, kind: usage.Use, start: dt.datetime, end: dt.datetime, first: dt.date) -> list[float | None]:
    """The use of one resource on each of the thirty days from `first`, from the metrics of its kind in daily buckets of Azure Monitor (the days between `start` and `end`, UTC), or an HttpError
    (also for a bucket that is not a UTC day: that is an answer of another shape than the one that Learn documents, and the History says so).
    A kind that takes the larger of its metrics does without one that the resource does not have (Azure answers 400 for a name that it does not offer for that resource) and fails on any other
    answer, so that a failed read is never a day of nothing; a kind that adds its metrics needs every one of them."""
    parts: list[list[float | None]] = []
    missing: HttpError | None = None
    for metric in kind.metrics:
        try:
            _, points = arm.metrics(resource_id, metric, start, end)
        except HttpError as error:
            if kind.combine != "max" or error.status != 400:
                raise
            missing = missing or error
            continue
        if any(usage.day_of(point.time) is None for point in points):  # a bucket that is not a UTC day is an answer that the app does not understand, and not a day without a value
            raise HttpError(200, "Azure Monitor gave a bucket that is not a UTC day")
        parts.append(usage.daily(((point.time, getattr(point, kind.aggregate)) for point in points), first, usage.DAYS))
    if not parts:
        raise missing if missing is not None else HttpError(0, "the use of the resource has no metric to read")
    return usage.combine(parts, kind.combine)


def _read_use(s: Services, ex: "wiring.Extras", say: Callable[[str], None]) -> None:
    last = s.clock().astimezone(dt.timezone.utc).date() - dt.timedelta(days=1)
    first = last - dt.timedelta(days=usage.DAYS - 1)
    start, end = (dt.datetime.combine(day, dt.time.min, tzinfo=dt.timezone.utc) for day in (first, last + dt.timedelta(days=1)))  # the thirty closed days, as UTC days
    due: dict[str, tuple[usage.Use, list[CaseRecord]]] = {}
    seen: set[str] = set()
    for plan in ex.store.plans_open():
        case = ex.store.case_get(plan.case_id)
        if case is None or case.case_id in seen:
            continue
        seen.add(case.case_id)
        kind = usage.for_resource(case.resource_id, case.resource_type)
        if kind is None or (isinstance(case.facts, dict) and GROUP_FACT in case.facts):  # a case that stands for many resources has no use of its own
            continue
        if case.use_series_end == last.isoformat() and case.use_kind == kind.kind and len(case.use_series or ()) == usage.DAYS:
            continue
        due.setdefault(case.resource_id.lower(), (kind, []))[1].append(case)
    ranked = sorted(due.values(), key=lambda item: min(case.use_series_end or "" for case in item[1]))  # a resource that was never read goes first, then the one read longest ago
    chosen, waiting = ranked[:USE_MAX_RESOURCES], sum(len(cases) for _, cases in ranked[USE_MAX_RESOURCES:])
    failed = late = 0
    why = ""
    for position, (kind, cases) in enumerate(chosen):
        left = s.client.remaining()  # the clock of the run's deadline
        if left is not None and left < USE_MIN_SECONDS:
            late = sum(len(rest) for _, rest in chosen[position:])
            break
        try:
            series = _read_use_of(s.arm, cases[0].resource_id, kind, start, end, first)
        except HttpError as error:
            why = why or clean_text(s.redact(error), 200)
            failed += len(cases)
            if error.status == 429:
                failed += sum(len(rest) for _, rest in chosen[position + 1:])  # a limit ends the step: the others are not asked
                break
            continue
        if usage.days_with_value(series) < usage.MIN_DAYS:
            continue
        try:
            for case in cases:
                ex.store.case_update(case.case_id, lambda kept: replace(kept, use_series=series, use_series_end=last.isoformat(), use_kind=kind.kind))  # only these fields, on the case as it is stored now
        except StoreError as error:
            why = why or clean_text(s.redact(error), 200)
            failed += len(cases)
    if failed:
        say(f"the use of {failed} open request{'' if failed == 1 else 's'} could not be read ({why}); what was read before stays")
    if late:
        say(f"the use of {late} open request{'' if late == 1 else 's'} was not read: the run had too little time left")
    if waiting:
        say(f"{waiting} more open request{'' if waiting == 1 else 's'} {'waits' if waiting == 1 else 'wait'} for the next search: at most {USE_MAX_RESOURCES} resources are read in one search")


def read_use_series(s: Services, say: Callable[[str], None]) -> None:
    """The step after read_cost_series: reads the use (CaseRecord.use_series) of each case with an open plan whose series is missing or does not end yesterday, for a case of one resource of a
    type that the table of cases/usage.py has. The days are the thirty closed days to yesterday (UTC), a day that Azure Monitor has no value for is a gap, and nothing is stored unless
    usage.MIN_DAYS of the days have a value. At most USE_MAX_RESOURCES resources are read in a Watch, and none when the run has less than USE_MIN_SECONDS left. A failure leaves the case as it
    was and is one line in the History for its kind of problem; a limit ends the step. It only reads, and it never fails the run."""
    ex = s.extras
    if ex is None:
        return
    try:
        _read_use(s, ex, say)
    except Exception as error:  # noqa: BLE001 (this step never stops the run)
        say(f"the use of the open requests could not be read ({clean_text(s.redact(f'{type(error).__name__}: {error}'), 200)})")


def _keep_requests_up_to_date(s: Services, ranked: Sequence[Lead], say: Callable[[str], None]) -> None:
    """Gives the open requests what this Watch learned since they were made: the name of the subscription, Advisor's words and the cost (cases/upkeep.py refresh). It writes the records of the
    app only, and it never fails the run."""
    try:
        upkeep.refresh(s.extras.store, ranked)
    except Exception as error:  # noqa: BLE001 (this step never stops the run)
        say(f"the open requests could not be brought up to date ({clean_text(s.redact(f'{type(error).__name__}: {error}'), 200)})")


def _take_back_empty(s: Services, say: Callable[[str], None]) -> Counter:
    """Takes back the open requests that cannot say what to look at, that a rule holds back or that were made under rules that have changed (cases/upkeep.py take_back), and returns how many there
    were of each reason, in the words of the History. It never fails the run."""
    try:
        return upkeep.take_back(s.extras, s.history)
    except Exception as error:  # noqa: BLE001 (this step never stops the run)
        say(f"the requests that say nothing could not be taken back ({clean_text(s.redact(f'{type(error).__name__}: {error}'), 200)})")
        return Counter()


def execute(s: Services, trigger: str) -> Summary:
    h, st = s.history, s.settings
    started = s.monotonic()
    deadline = started + st.deadline_seconds
    s.client.deadline = deadline
    summary = Summary()
    notes: list[str] = []
    started_at = stamp(s.clock())
    investigated = False  # set when the investigation has run: the record of the run says so, and the timer counts its days from it

    def keep(finished: bool, reason: str | None = None) -> RunRecord | None:
        """The run goes to the store, when there is one. A store that fails never stops the run."""
        if s.extras is None:
            return None
        record = RunRecord(
            run_id=h.run_id, trigger=trigger, started_at=started_at, finished_at=stamp(s.clock()) if finished else None, ok=summary.ok and reason is None,
            leads=summary.leads, cases=summary.cases, proposed=summary.proposed, needs_human=summary.needs_human, dropped=summary.dropped, errors=summary.errors,
            tokens=summary.tokens, seconds=summary.seconds, notes=tuple(clean_text(n, 300) for n in notes[:20]), reason=reason, investigated=investigated, held=summary.held)
        try:
            s.extras.store.run_put(record)
        except StoreError as error:
            LOG.warning(s.redact(f"the run could not be kept in the store: {error}"))
        return record

    # The subscriptions of this run are listed once, here. Every later read, the tools of the investigation and the History work with this list (a copy of the settings that
    # holds it), so that they cannot differ. What a change may touch does not depend on it: plans and changes are keyed on the resource groups of the change scopes.
    loop_subscriptions = tuple(dict.fromkeys(scope.subscription for scope in s.extras.settings.change_scopes)) if s.extras is not None else ()
    refusal = None
    try:
        scope = scope_mod.resolve(s.arm, st, loop_subscriptions, s.redact)
    except scope_mod.ScopeError as error:
        scope, refusal = scope_mod.Scope((), "none"), clean_text(s.redact(error), 300)
    notes.extend(scope.notes)
    st = replace(st, subscriptions=scope.subscriptions, quota_ids=scope.quotas)
    s = replace(s, settings=st)
    # With many subscriptions the line carries their count and the first few ids, not all of them.
    h.emit("run.started", trigger=trigger, subscriptions=len(scope.subscriptions), scopes=[x[:8] for x in scope.subscriptions[:SCOPES_SHOWN]], scopeFrom=scope.source,
           detectors=list(DETECTOR_NAMES))
    keep(False)
    s.models.open()
    if refusal:
        for note in notes:
            h.emit("run.note", note=clean_text(note, 300))
        h.emit("run.failed", reason=refusal)
        summary.ok = False
        keep(True, refusal)
        return summary

    # The share of the deadline for reading: the subscriptions of the loop first (the waste that Meternaut plants itself is there), then the others in the order of their ids.
    read_deadline = started + READ_SHARE * st.deadline_seconds
    s.client.deadline = min(deadline, started + (READ_SHARE + READ_GRACE) * st.deadline_seconds)
    estate = detectors.collect_estate(s.arm, sorted(st.subscriptions, key=lambda sub: sub not in loop_subscriptions), s.clock(), notes,
                                      out_of_time=lambda: s.monotonic() >= read_deadline)
    s.client.deadline = deadline
    found: list[Lead] = estate.leads
    contexts: dict[str, Context] = estate.contexts
    read = estate.sources_read
    notes.extend(_currency_notes(contexts))
    if estate.unread:
        notes.append(_unread_note(estate, st.deadline_seconds))
    for note in notes:
        h.emit("run.note", note=clean_text(note, 300))
    if read == 0:
        too_late = s.monotonic() >= deadline
        if too_late:
            reason = f"the deadline of {st.deadline_seconds} seconds was reached before any detector could read"
        elif estate.stopped == "time":
            reason = f"the time for reading the subscriptions ({int(READ_SHARE * st.deadline_seconds)} of the {st.deadline_seconds} seconds of the run) was used up before any detector could read"
        else:
            reason = "no detector could read any subscription"
        h.emit("run.failed", reason=reason)
        summary.ok = False
        keep(True, reason)
        return summary

    ranked = detectors.rank(found, contexts)
    approval = wiring.approval_settings(s.extras.settings) if s.extras is not None else None

    def planted(lead: Lead) -> bool:
        """Waste that Meternaut planted itself in the one group where a change may be made: the loop is proved on it, so it still goes through the two roles."""
        return approval is not None and is_fixture(lead, approval)

    if approval is not None:
        ranked = sorted(ranked, key=lambda lead: not planted(lead))  # stable: the waste that Meternaut planted itself goes first, it is the one kind that a change may be made on
    summary.leads = len(ranked)
    for position, lead in enumerate(ranked[:MAX_LEAD_EVENTS], 1):
        h.emit("lead.found", leadId=lead.lead_id, detector=lead.detector, resourceId=lead.resource_id, resourceType=clean_text(lead.resource_type, 120),
               resourceName=clean_text(lead.name, 120), resourceGroup=clean_text(lead.resource_group, 90), costUsd30d=lead.cost_usd_30d, rank=position)
    if len(ranked) > MAX_LEAD_EVENTS:
        counts = Counter(lead.detector for lead in ranked[MAX_LEAD_EVENTS:])
        h.emit("run.note", note=f"{len(ranked) - MAX_LEAD_EVENTS} more leads are not listed: " + ", ".join(f"{name} {n}" for name, n in sorted(counts.items())))

    def say(text: str) -> None:
        notes.append(text)
        h.emit("run.note", note=clean_text(text, 300))

    # The investigation goes first, with a budget and a time of its own: what it takes is not taken from the deadline of the cases after it.
    before = s.monotonic()
    waits = investigation_wait(s, trigger)
    if waits is None:
        investigation = investigate.investigate(s, contexts, notes)
    else:
        investigation = investigate.Investigation(off=True, note=waits)
    investigated = investigation.ran
    if investigated:
        keep(False)  # the money is spent: the clock starts now, and a fault or a restart later in the run does not make the timer pay for another investigation tomorrow
    deadline += s.monotonic() - before
    s.client.deadline = deadline
    summary.cases += investigation.cases
    summary.proposed += investigation.proposed
    summary.needs_human += investigation.needs_human
    summary.dropped += investigation.dropped
    summary.errors += investigation.errors
    if s.extras is not None:
        closed = s.extras.approvals.supersede()
        if closed:
            say(f"{len(closed)} earlier request{'s' if len(closed) != 1 else ''} about single resources {'were' if len(closed) != 1 else 'was'} closed: the request for the group of resources that "
                f"{'they belong' if len(closed) != 1 else 'it belongs'} to waits")
    candidates = ranked
    if investigation.ran or investigation.held:
        # The investigation found the waste by itself, so the leads of the fixed detectors that are real resources are left to it. They stay in the History as leads. When the harness held
        # the investigation (a pulled switch, a lock that does not hold, a stored definition that differs) no new case of the investigation is opened, and these leads are not judged by the
        # two roles either: only the waste that Meternaut planted itself goes on, so that the loop stays proved.
        candidates = [lead for lead in ranked if planted(lead)]
        left_to_it = len(ranked) - len(candidates)
        if investigation.held:
            say(f"the investigation is held: {investigation.note}")
        if left_to_it:
            say(f"{left_to_it} lead{'s were' if left_to_it != 1 else ' was'} left to the investigation and not judged by the Detective and the Skeptic")
    else:
        say(f"the investigation did not run: {investigation.note}")

    tokens = 0
    wanted: list[Lead] = []
    skipped = 0
    for lead in candidates:
        if len(wanted) >= st.max_cases:
            break
        if _recently_judged(s, lead):
            skipped += 1
            continue
        wanted.append(lead)
    if skipped:
        note = f"{skipped} lead{'s were' if skipped != 1 else ' was'} judged within the last {s.extras.settings.recheck_days} days and not taken up again"
        notes.append(note)
        h.emit("run.note", note=note)
    held_ids: list[str] = []
    for number, lead in enumerate(wanted, 1):
        left = len(wanted) - number + 1
        if s.monotonic() >= deadline:
            h.emit("run.note", note=f"the deadline of {st.deadline_seconds} seconds was reached; {_cases(left)} not taken up")
            break
        if tokens + st.max_completion_tokens + PROMPT_TOKEN_RESERVE > st.max_tokens_per_run:
            h.emit("run.note", note=f"the token budget of {st.max_tokens_per_run} for the run was reached; {_cases(left)} not taken up")
            break
        status, used = work_case(s, number, lead, contexts.get(lead.subscription_id, Context()), tokens, held_ids)
        tokens += used
        summary.cases += 1
        if status == "proposed":
            summary.proposed += 1
        elif status == "needs_human":
            summary.needs_human += 1
        elif status == "dropped":
            summary.dropped += 1
        else:
            summary.errors += 1
    held = Counter(held_ids)  # the words of the History for each finding that was held back by a case of this Watch
    held[NOTHING_TO_SAY] += investigation.said_nothing
    held.update({HELD_BACK[why]: count for why, count in investigation.held_back.items()})
    if s.extras is not None:
        _keep_requests_up_to_date(s, ranked, say)  # what open requests show: the names, Advisor's words and the cost that this Watch read
        held.update(_take_back_empty(s, say))  # the requests that cannot say what to look at, that a rule holds back or that were made under rules that have changed, are taken back before the cost of the others is read
    summary.held += sum(held.values())
    for reason, count in held.items():
        if count:
            say(f"{count} finding{'s' if count != 1 else ''} {reason}")
    read_cost_series(s, contexts, say)
    read_use_series(s, say)
    summary.tokens = tokens
    summary.seconds = int(s.monotonic() - started)
    h.emit("run.finished", ok=summary.ok, leads=summary.leads, cases=summary.cases, proposed=summary.proposed, needsHuman=summary.needs_human,
           dropped=summary.dropped, errors=summary.errors, tokens=summary.tokens, seconds=summary.seconds, investigation=investigation.state,
           investigationLines=h.lines("investigation."), heldBack=summary.held)
    finished = keep(True)
    if finished is not None and s.extras is not None:
        try:
            s.extras.on_run(finished)
        except Exception as error:  # noqa: BLE001 (a letter never stops the run)
            LOG.warning(s.redact(f"the weekly desk could not be sent: {type(error).__name__}"))
    return summary


def run_watch(trigger: str, request_id: str | None, env: Mapping[str, str] | None = None, *, clock: Callable[[], dt.datetime] = utc_now,
              monotonic: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep, transport=default_transport, fetch=None,
              new_id: Callable[[], str] = lambda: uuid.uuid4().hex, extras: "wiring.Extras | None" = None, foundry: "Foundry | None" = None,
              harness: "harness_module.Harness | None" = None) -> Summary:
    """The whole run, with a History line for whatever goes wrong. It never raises: the History says how the run ended.

    `extras` is the loop (the store, the people, the approvals); None builds it from the settings, and a run without the settings of the loop is the Watch alone.
    `foundry` is the client of the Foundry project of the investigation; None builds it from the settings, and without an endpoint there is none. The harness around its agents is built
    with it (cases/harness.py): a caller that hands in a client of its own hands in the harness too, or none."""
    env = os.environ if env is None else env
    redact = Redactor()
    history = History(new_id(), request_id, clock, redact)
    try:
        settings = cfg.load(env)
        identity = Identity(env, sleep=sleep, **({"fetch": fetch} if fetch else {}))
        client = Client(allowed_calls(foundry_endpoint=settings.foundry_endpoint, ai_gateway_host=settings.ai_gateway_host), redact, transport=transport, sleep=sleep, monotonic=monotonic)
        if extras is None:
            extras = wiring.build_extras(env, identity.token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
        if foundry is None and settings.foundry_endpoint:
            foundry = Foundry(settings.foundry_endpoint, client, identity.token, redact)
            harness = harness_module.build(settings, foundry, extras, env=env, clock=clock, monotonic=monotonic, redact=redact)
        services = Services(settings, client, Arm(client, identity.token), Models(settings, client, identity.token, redact), history, redact, clock, monotonic, extras,
                            foundry, harness)
        return execute(services, trigger)
    except Exception as error:  # noqa: BLE001 (the History must say how every run ended)
        reason = clean_text(redact(f"{type(error).__name__}: {error}"), 300)
        history.emit("run.failed", reason=reason)
        LOG.error(redact(f"the run failed: {reason}"))
        return Summary(ok=False)
