"""One run of the Watch: find leads, let the investigation look for waste by itself, take the leads that are left through the two model roles, apply the guards,
write the History.

Nothing here changes Azure. The limits of docs/proposals/02-first-cases.md are applied here: the cases per run, the tokens per run and per
call, the deadline, the retries (in http.py) and the refusals of the gateway. The investigation (investigate.py) has a budget of its own, and the time that it
takes is not taken from the deadline of the cases that follow it.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Mapping

from . import config as cfg
from . import decide, detectors, evidence, guards, investigate, roles, wiring
from .approvals import is_fixture
from .arm import Arm, scopes_of
from .detectors import DETECTOR_NAMES, Context, Lead
from .events import History
from .evidence import EvidenceError
from .foundry import Foundry
from .gateway import Gateway, GatewayError
from .http import Client, HttpError, allowed_calls, default_transport
from .identity import Identity, IdentityError
from .memory_store import stamp
from .models import CaseRecord, RunRecord, StoreError
from .redact import Redactor
from .roles import RoleError, clean_text

MAX_LEAD_EVENTS = 50
PROMPT_TOKEN_RESERVE = 2000
LOG = logging.getLogger("meternaut.run")


@dataclass
class Services:
    settings: cfg.Settings
    client: Client
    arm: Arm
    gateway: Gateway
    history: History
    redact: Redactor
    clock: Callable[[], dt.datetime]
    monotonic: Callable[[], float]
    extras: "wiring.Extras | None" = None
    foundry: "Foundry | None" = None


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


class CaseEnded(Exception):
    """A case that cannot go on; the text says why."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _figure(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _cases(number: int) -> str:
    return "1 case was" if number == 1 else f"{number} cases were"


def work_case(s: Services, number: int, lead: Lead, context: Context, tokens_before: int) -> tuple[str, int]:
    """One case, from the evidence to the result. Returns its status and the tokens that it used."""
    h, st = s.history, s.settings
    case_id = f"{h.run_id[:8]}-c{number}"
    used = 0
    h.emit("case.started", caseId=case_id, leadId=lead.lead_id)
    identity = {"caseId": case_id, "leadId": lead.lead_id, "detector": lead.detector, "resourceName": clean_text(lead.name, 120),
                "resourceType": clean_text(lead.resource_type, 120), "resourceGroup": clean_text(lead.resource_group, 90), "costUsd30d": lead.cost_usd_30d}
    steps: list[dict] = []
    models: dict[str, str | None] = {"detective": st.model_detective, "skeptic": None}

    def save(status: str, recommendation: str | None, confidence: float | None, saving: float | None, summary: str, objections: list[str], flags_on: list[str],
             facts: dict) -> None:
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
                recommendation=recommendation, confidence=confidence, saving_usd_month=saving, cost_usd_30d=lead.cost_usd_30d, summary=clean_text(summary, 600),
                objections=tuple(clean_text(o, 300) for o in objections), guards=tuple(flags_on), models=dict(models), steps=tuple(steps), facts=facts,
                first_seen_at=old.first_seen_at if old and old.first_seen_at else now, updated_at=now, runs_seen=(old.runs_seen + 1) if old else 1)
            ex.store.case_put(record)
            if status == "proposed":
                plan = ex.approvals.create(record, lead, ex.approvers())
                if plan is not None:
                    h.emit("plan.created", planId=plan.plan_id, caseKey=record.case_id, family=plan.family, approvers=len(plan.approvers))
                    ex.on_plan(plan, ex.store.case_get(record.case_id) or record)
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
            chat = s.gateway.chat(model, system, user, st.max_completion_tokens)
            used += chat.total_tokens
            answer = parse(chat.text)
        except (GatewayError, RoleError) as error:
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
         case["facts"])
    return outcome.status, used


def _recently_judged(s: Services, lead: Lead) -> bool:
    """A lead whose case was judged within the last days (and did not end in an error) is not taken up again: the slot goes to a lead that was not judged."""
    ex = s.extras
    if ex is None:
        return False
    try:
        old = ex.store.case_get(f"k{lead.lead_id}")
    except StoreError:
        return False
    if old is None or old.status == "error" or not old.updated_at:
        return False
    age = s.clock() - dt.datetime.strptime(old.updated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    return age < dt.timedelta(days=ex.settings.recheck_days)


def execute(s: Services, trigger: str) -> Summary:
    h, st = s.history, s.settings
    started = s.monotonic()
    deadline = started + st.deadline_seconds
    s.client.deadline = deadline
    summary = Summary()
    notes: list[str] = []
    started_at = stamp(s.clock())

    def keep(finished: bool, reason: str | None = None) -> RunRecord | None:
        """The run goes to the store, when there is one. A store that fails never stops the run."""
        if s.extras is None:
            return None
        record = RunRecord(
            run_id=h.run_id, trigger=trigger, started_at=started_at, finished_at=stamp(s.clock()) if finished else None, ok=summary.ok and reason is None,
            leads=summary.leads, cases=summary.cases, proposed=summary.proposed, needs_human=summary.needs_human, dropped=summary.dropped, errors=summary.errors,
            tokens=summary.tokens, seconds=summary.seconds, notes=tuple(clean_text(n, 300) for n in notes[:20]), reason=reason)
        try:
            s.extras.store.run_put(record)
        except StoreError as error:
            LOG.warning(s.redact(f"the run could not be kept in the store: {error}"))
        return record

    h.emit("run.started", trigger=trigger, scopes=[x[:8] for x in st.subscriptions], detectors=list(DETECTOR_NAMES))
    keep(False)
    try:
        s.gateway.open()
    except GatewayError as error:
        reason = clean_text(s.redact(error), 300)
        h.emit("run.failed", reason=reason)
        summary.ok = False
        keep(True, reason)
        return summary

    found: list[Lead] = []
    contexts: dict[str, Context] = {}
    read = 0
    for subscription in st.subscriptions:
        try:
            collected = detectors.collect(s.arm, subscription, s.clock(), notes)
        except (IdentityError, HttpError) as error:
            notes.append(f"{subscription[:8]}: the subscription could not be read ({s.redact(error)})")
            continue
        read += collected.sources_read
        found += collected.leads
        contexts[subscription] = collected.context
        if collected.context.currency not in (None, "USD"):
            notes.append(f"{subscription[:8]}: the cost lines are in {collected.context.currency}, so no figure is shown in US dollars")
    for note in notes:
        h.emit("run.note", note=clean_text(note, 300))
    if read == 0:
        too_late = s.monotonic() >= deadline
        reason = (f"the deadline of {st.deadline_seconds} seconds was reached before any detector could read" if too_late else "no detector could read any subscription")
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
    investigation = investigate.investigate(s, contexts, notes)
    deadline += s.monotonic() - before
    s.client.deadline = deadline
    summary.cases += investigation.cases
    summary.proposed += investigation.proposed
    summary.needs_human += investigation.needs_human
    summary.dropped += investigation.dropped
    summary.errors += investigation.errors
    candidates = ranked
    if investigation.ran:
        # The investigation found the waste by itself, so the leads of the fixed detectors that are real resources are left to it. They stay in the History as leads.
        candidates = [lead for lead in ranked if planted(lead)]
        left_to_it = len(ranked) - len(candidates)
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
    for number, lead in enumerate(wanted, 1):
        left = len(wanted) - number + 1
        if s.monotonic() >= deadline:
            h.emit("run.note", note=f"the deadline of {st.deadline_seconds} seconds was reached; {_cases(left)} not taken up")
            break
        if tokens + st.max_completion_tokens + PROMPT_TOKEN_RESERVE > st.max_tokens_per_run:
            h.emit("run.note", note=f"the token budget of {st.max_tokens_per_run} for the run was reached; {_cases(left)} not taken up")
            break
        status, used = work_case(s, number, lead, contexts.get(lead.subscription_id, Context()), tokens)
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
    summary.tokens = tokens
    summary.seconds = int(s.monotonic() - started)
    h.emit("run.finished", ok=summary.ok, leads=summary.leads, cases=summary.cases, proposed=summary.proposed, needsHuman=summary.needs_human,
           dropped=summary.dropped, errors=summary.errors, tokens=summary.tokens, seconds=summary.seconds)
    finished = keep(True)
    if finished is not None and s.extras is not None:
        try:
            s.extras.on_run(finished)
        except Exception as error:  # noqa: BLE001 (a letter never stops the run)
            LOG.warning(s.redact(f"the weekly desk could not be sent: {type(error).__name__}"))
    return summary


def run_watch(trigger: str, request_id: str | None, env: Mapping[str, str] | None = None, *, clock: Callable[[], dt.datetime] = utc_now,
              monotonic: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep, transport=default_transport, fetch=None,
              new_id: Callable[[], str] = lambda: uuid.uuid4().hex, extras: "wiring.Extras | None" = None, foundry: "Foundry | None" = None) -> Summary:
    """The whole run, with a History line for whatever goes wrong. It never raises: the History says how the run ended.

    `extras` is the loop (the store, the people, the approvals); None builds it from the settings, and a run without the settings of the loop is the Watch alone.
    `foundry` is the client of the Foundry project of the investigation; None builds it from the settings, and without an endpoint there is none."""
    env = os.environ if env is None else env
    redact = Redactor()
    history = History(new_id(), request_id, clock, redact)
    try:
        settings = cfg.load(env)
        identity = Identity(env, **({"fetch": fetch} if fetch else {}))
        client = Client(allowed_calls(settings.gateway_host, Gateway.key_path(settings), foundry_endpoint=settings.foundry_endpoint), redact, transport=transport,
                        sleep=sleep, monotonic=monotonic)
        if extras is None:
            extras = wiring.build_extras(env, identity.token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
        if foundry is None and settings.foundry_endpoint:
            foundry = Foundry(settings.foundry_endpoint, client, identity.token, redact)
        services = Services(settings, client, Arm(client, identity.token), Gateway(settings, client, identity.token, redact), history, redact, clock, monotonic, extras,
                            foundry)
        return execute(services, trigger)
    except Exception as error:  # noqa: BLE001 (the History must say how every run ended)
        reason = clean_text(redact(f"{type(error).__name__}: {error}"), 300)
        history.emit("run.failed", reason=reason)
        LOG.error(redact(f"the run failed: {reason}"))
        return Summary(ok=False)
