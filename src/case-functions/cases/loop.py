"""The timer of the loop, every minute: closes the plans whose time is over, makes the changes whose start time has come, checks the changes that were made,
and tells the person what happened. It does nothing when the loop is not configured, and nothing when a switch is pulled (runner.py reads them).
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import time
import uuid
from typing import Callable, Mapping

from . import config as cfg
from . import loop_config, runner, wiring
from .arm import Arm
from .events import History
from .gateway import Gateway
from .http import Client, allowed_calls, default_transport
from .identity import Identity
from .memory_store import utc_now
from .redact import Redactor
from .runner import RunnerServices, TickResult, runner_calls

LOG = logging.getLogger("meternaut.loop")


def tick(env: Mapping[str, str] | None = None, *, transport=default_transport, sleep: Callable[[float], None] = time.sleep,
         monotonic: Callable[[], float] = time.monotonic, clock: Callable[[], dt.datetime] = utc_now, fetch=None) -> TickResult | None:
    """One round. It never raises: a failure is logged, and the next minute tries again."""
    env = os.environ if env is None else env
    redact = Redactor()
    try:
        settings = loop_config.load(env)
        if settings is None:
            return None
        watch = cfg.load(env)
        options = {"fetch": fetch} if fetch else {}
        reader = Identity(env, **options)
        writer = Identity({**env, "AZURE_CLIENT_ID": settings.writer_client_id}, **options)
        extras = wiring.build_extras(env, reader.token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
        if extras is None:
            return None
        runner_client = Client(runner_calls(settings.writer_subscription, settings.writer_group), redact, transport=transport, sleep=sleep, monotonic=monotonic)
        reader_client = Client(allowed_calls(watch.gateway_host, Gateway.key_path(watch)), redact, transport=transport, sleep=sleep, monotonic=monotonic)
        history = History(uuid.uuid4().hex, None, clock, redact)
        services = RunnerServices(extras.store, runner_client, writer.token, wiring.approval_settings(settings), settings.writer_subscription,
                                  arm=Arm(reader_client, reader.token), clock=clock, sleep=sleep, emit=history.emit)
        result = runner.tick(services)
        for action in result.finished + result.verified:
            plan = extras.store.plan_get(action.plan_id)
            case = extras.store.case_get(action.case_id)
            try:
                extras.on_action(action, plan, case)
            except Exception as error:  # noqa: BLE001 (a letter that fails never undoes a change)
                LOG.error(redact(f"a letter about {action.state} could not be sent: {type(error).__name__}"))
        if clock().minute == 0:
            purge = getattr(extras.store, "nonces_purge", None)
            if purge:
                purge()
        if result.expired or result.finished or result.verified:
            history.emit("tick.result", expired=len(result.expired), finished=len(result.finished), verified=len(result.verified))
        return result
    except Exception as error:  # noqa: BLE001 (the timer must go on)
        LOG.error(redact(f"the tick failed: {type(error).__name__}: {error}"))
        return None
