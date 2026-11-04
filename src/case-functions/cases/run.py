"""One run of the Watch: find leads, take the dearest ones through the two model roles, apply the guards, write the History.

Nothing here changes Azure. The limits of docs/proposals/02-first-cases.md are applied here: the cases per run, the tokens per run and per
call, the deadline, the retries (in http.py) and the refusals of the gateway.
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
from . import decide, detectors, evidence, guards, roles
from .arm import Arm, scopes_of
from .detectors import DETECTOR_NAMES, Context, Lead
from .events import History
from .evidence import EvidenceError
from .gateway import Gateway, GatewayError
from .http import Client, HttpError, allowed_calls, default_transport
from .identity import Identity, IdentityError
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

    def ended(note: str) -> tuple[str, int]:
        h.emit("case.result", **identity, status="error", recommendation=None, confidence=None, monthlySavingUsd=None, summary=note, objections=[], guards=[])
        return "error", used

    def step(name: str, model: str | None, started: float, ok: bool, note: str | None = None, chat_tokens: tuple[int, int] | None = None) -> None:
        h.emit("case.step", caseId=case_id, step=name, model=model, promptTokens=chat_tokens[0] if chat_tokens else None,
               completionTokens=chat_tokens[1] if chat_tokens else None, ms=int((s.monotonic() - started) * 1000), ok=ok, note=note)

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
    flags = guards.evaluate(lead, context, scope_locks)
    try:
        case = evidence.case_dto(number, lead, flags)
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
    return outcome.status, used


def execute(s: Services, trigger: str) -> Summary:
    h, st = s.history, s.settings
    started = s.monotonic()
    deadline = started + st.deadline_seconds
    s.client.deadline = deadline
    summary = Summary()
    h.emit("run.started", trigger=trigger, scopes=[x[:8] for x in st.subscriptions], detectors=list(DETECTOR_NAMES))
    try:
        s.gateway.open()
    except GatewayError as error:
        h.emit("run.failed", reason=clean_text(s.redact(error), 300))
        summary.ok = False
        return summary

    notes: list[str] = []
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
        h.emit("run.failed", reason=(f"the deadline of {st.deadline_seconds} seconds was reached before any detector could read" if too_late
                                     else "no detector could read any subscription"))
        summary.ok = False
        return summary

    ranked = detectors.rank(found, contexts)
    summary.leads = len(ranked)
    for position, lead in enumerate(ranked[:MAX_LEAD_EVENTS], 1):
        h.emit("lead.found", leadId=lead.lead_id, detector=lead.detector, resourceId=lead.resource_id, resourceType=clean_text(lead.resource_type, 120),
               resourceName=clean_text(lead.name, 120), resourceGroup=clean_text(lead.resource_group, 90), costUsd30d=lead.cost_usd_30d, rank=position)
    if len(ranked) > MAX_LEAD_EVENTS:
        counts = Counter(lead.detector for lead in ranked[MAX_LEAD_EVENTS:])
        h.emit("run.note", note=f"{len(ranked) - MAX_LEAD_EVENTS} more leads are not listed: " + ", ".join(f"{name} {n}" for name, n in sorted(counts.items())))

    tokens = 0
    wanted = ranked[:st.max_cases]
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
    return summary


def run_watch(trigger: str, request_id: str | None, env: Mapping[str, str] | None = None, *, clock: Callable[[], dt.datetime] = utc_now,
              monotonic: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep, transport=default_transport, fetch=None,
              new_id: Callable[[], str] = lambda: uuid.uuid4().hex) -> Summary:
    """The whole run, with a History line for whatever goes wrong. It never raises: the History says how the run ended."""
    env = os.environ if env is None else env
    redact = Redactor()
    history = History(new_id(), request_id, clock, redact)
    try:
        settings = cfg.load(env)
        identity = Identity(env, **({"fetch": fetch} if fetch else {}))
        client = Client(allowed_calls(settings.gateway_host, Gateway.key_path(settings)), redact, transport=transport, sleep=sleep, monotonic=monotonic)
        services = Services(settings, client, Arm(client, identity.token), Gateway(settings, client, identity.token, redact), history, redact, clock, monotonic)
        return execute(services, trigger)
    except Exception as error:  # noqa: BLE001 (the History must say how every run ended)
        reason = clean_text(redact(f"{type(error).__name__}: {error}"), 300)
        history.emit("run.failed", reason=reason)
        LOG.error(redact(f"the run failed: {reason}"))
        return Summary(ok=False)
