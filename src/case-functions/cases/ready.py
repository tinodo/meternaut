"""The job `ready`: makes the stored version of each of the three agents from the lock, before any run (docs/proposals/11-agent-harness-and-evaluation.md, "The order of a release").

A control message with the job `ready` (cases/control.py) makes the Investigator, the Skeptic and the Scholar ready through the harness that every run uses (cases/harness.py): the same lock,
the same switches, the same stored definition read back, and the same refusals with the same words. It calls no model, makes no investigation and reads nothing of the estate: its client may only
read an agent and make one (the first three calls of http.foundry_calls). Each agent gets one line `agents.ready` and the end gets `agents.ready.finished` (events.READY_KINDS), with typed values
only: the name of one of the three agents, its version, 12 hex digits of the lock's digest of its definition, and `made` (this job made the version), `existing` (the stored latest version was
the one of the lock), `refused` (the harness said no) or `failed` (the service gave no answer), with one word for the reason.

What it does not say: that the version works (that is `foundry-evals`), or that a run will use it as it is (a run uses the latest version of each agent; nothing splits the traffic).
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from collections import Counter
from typing import Callable, Mapping

from . import agents, config as cfg, harness as harness_module, library, toolbox, wiring
from .events import History
from .foundry import Foundry, FoundryError, Made
from .harness import HarnessRefused
from .http import Client, default_transport, foundry_calls
from .identity import Identity
from .memory_store import utc_now
from .redact import Redactor
from .roles import clean_text

LOG = logging.getLogger("meternaut.ready")
NAMES = (agents.INVESTIGATOR_NAME, agents.SKEPTIC_NAME, agents.SCHOLAR_NAME)
OUTCOMES = ("made", "existing", "refused", "failed")
SECONDS = 300  # the deadline of the job's calls: three agents take a few reads and writes each
# The reason words of a line: the codes of harness._refused, `service` when the Agent Service gave no answer and `other` for a code that is none of them.
REASONS = ("lock", "no-store", "switch", "lock-differs", "stored-unreadable", "stored-missing", "version-moved", "definition", "service", "other")
# Why the job could not begin: its settings or its client could not be made, there is no Foundry project, or something that nobody foresaw.
WHY = ("setup", "no-endpoint", "error")
DIGEST = re.compile(r"[0-9a-f]{12}")


def specs(settings: cfg.Settings) -> tuple:
    """The three agents as the investigation (cases/investigate.py) and the Study (cases/study.py) define them; the harness holds each against the lock before it makes it."""
    return agents.investigator(settings, toolbox.SPECS), agents.skeptic(settings), agents.scholar(settings, (library.FETCH_DOC,))


def make_ready(h: History, harness: "harness_module.Harness", spec) -> str:
    """Makes one agent ready and writes its line. Returns `made`, `existing`, `refused` or `failed`."""
    outcome, reason, version, status = "failed", "service", None, None
    try:
        reference = harness.ensure(spec)
    except HarnessRefused as refusal:
        outcome, reason = "refused", refusal.reason if refusal.reason in REASONS else "other"
    except FoundryError as error:
        status = error.status if isinstance(error.status, int) and not isinstance(error.status, bool) and 100 <= error.status <= 599 else None
    else:
        outcome, reason = "made" if isinstance(reference, Made) else "existing", ""
        number = reference.partition(":")[2]
        version = int(number) if number.isdigit() and len(number) <= 6 else None
    digest = harness.lock.definition_sha256(spec.name)[:12] if harness.lock is not None else ""
    h.emit("agents.ready", agent=spec.name, version=version, definition=digest if DIGEST.fullmatch(digest) else "", outcome=outcome, **({"reason": reason} if reason else {}),
           **({"status": status} if status else {}))
    return outcome


def execute(h: History, settings: "cfg.Settings | None", harness: "harness_module.Harness | None", monotonic: Callable[[], float] = time.monotonic, why: str = "") -> Counter:
    """Makes the three agents ready, one line for each, and writes the end line. It never raises: `why` or the end line says how it ended. A harness of None means that there is no Foundry
    project, and `why` is given by a caller that could not set the job up."""
    began, done = monotonic(), Counter()
    why = why or ("" if harness is not None else "no-endpoint")
    try:
        if not why:
            for spec in specs(settings):  # type: ignore[arg-type]
                done[make_ready(h, harness, spec)] += 1  # type: ignore[arg-type]
    except Exception as error:  # noqa: BLE001 (a job of the control queue never stops the app)
        why = "error"
        LOG.warning("the agents could not be made ready: %s", type(error).__name__)
    finally:
        if harness is not None:
            harness.close()  # the line `harness.run` of an agent that was refused, and the brake for a stored definition that differs
        h.emit("agents.ready.finished", ok=not why and done["made"] + done["existing"] == len(NAMES), **{word: done[word] for word in OUTCOMES}, why=why, seconds=int(monotonic() - began))
    return done


def run_ready(trigger: str, request_id: str | None, env: Mapping[str, str] | None = None, *, clock=utc_now, monotonic: Callable[[], float] = time.monotonic,
              sleep: Callable[[float], None] = time.sleep, transport=default_transport, fetch=None, new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
              extras: "wiring.Extras | None" = None) -> Counter:
    """The whole job. It never raises: the end line says how it ended. `trigger` is what started it (the control message) and is not recorded: nothing else starts it. `extras` is the loop, whose
    store keeps the switches; None builds it from the settings. The agents are made through the client of the Foundry project that this builds, and through no other."""
    env = os.environ if env is None else env
    redact = Redactor()
    history = History(new_id(), request_id, clock, redact)
    harness = None
    try:
        settings = cfg.load(env)
        if settings.foundry_endpoint:
            identity = Identity(env, sleep=sleep, **({"fetch": fetch} if fetch else {}))
            client = Client(foundry_calls(settings.foundry_endpoint)[:3], redact, transport=transport, sleep=sleep, monotonic=monotonic)
            client.deadline = monotonic() + SECONDS
            if extras is None:
                extras = wiring.build_extras(env, identity.token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
            foundry = Foundry(settings.foundry_endpoint, client, identity.token, redact)
            harness = harness_module.build(settings, foundry, extras, env=env, clock=clock, monotonic=monotonic, redact=redact)
    except Exception as error:  # noqa: BLE001 (a job of the control queue never stops the app)
        LOG.warning("the agents could not be made ready: %s", clean_text(redact(f"{type(error).__name__}: {error}"), 300))
        return execute(history, None, None, monotonic, "setup")
    return execute(history, settings, harness, monotonic)
