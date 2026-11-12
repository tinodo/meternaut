"""The timer of the loop, every minute: closes the plans whose time is over, checks the changes that were made, tells the person what happened and, every fifth minute, writes the lessons
of the plans that ended (cases/learning.py). It does nothing when the loop is not configured. It cannot change Azure: its token is the reader's, and its list of calls holds no write
(runner.py reads them).
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import time
import uuid
from typing import Callable, Mapping

from . import config as cfg
from . import learning, loop_config, runner, wiring
from .arm import Arm
from .events import History
from .http import Client, allowed_calls, default_transport
from .identity import Identity
from .memory_store import parse, utc_now
from .redact import Redactor
from .runner import RunnerServices, TickResult, read_calls

LOG = logging.getLogger("meternaut.loop")
LETTER_DAYS = 3  # the letters about a change are offered again for this long after it


def _offer_cards(extras: wiring.Extras, redact: Callable[[str], str]) -> None:
    """Offers the Teams cards that are due, before the letters (a person who chose Teams gets the card first: cases/offers.py). A card that fails never undoes a change and never stops the round."""
    try:
        extras.on_cards()
    except Exception as error:  # noqa: BLE001 (the timer must go on)
        LOG.error(redact(f"the cards could not be offered: {type(error).__name__}"))


def _remind(extras: wiring.Extras, clock: Callable[[], dt.datetime], redact: Callable[[str], str]) -> None:
    """Offers the letters about every open plan and about the changes of the last days (a result that is not known too: its hook holds the letter until the result has stayed so for a while).
    A hook sends a letter only when it is due, so a letter that was sent is never sent again and one that was held or failed is tried again later. A letter that fails never stops the round."""
    try:
        for plan in extras.store.plans_open():
            case = extras.store.case_get(plan.case_id) if plan.state == "open" else None
            if case is not None:
                extras.on_plan(plan, case)
        since = clock() - dt.timedelta(days=LETTER_DAYS)
        for action in extras.store.actions_recent(10):
            moment = action.finished_at or action.queued_at
            if action.state in ("done", "failed", "verified", "unknown") and moment and parse(moment) >= since:
                extras.on_action(action, extras.store.plan_get(action.plan_id), extras.store.case_get(action.case_id))
        extras.on_tick()  # the weekly summary and the letter of a trip that a person's quiet hours held back, once the hours are over
    except Exception as error:  # noqa: BLE001 (the timer must go on)
        LOG.error(redact(f"the letters could not be offered: {type(error).__name__}"))


def tick(env: Mapping[str, str] | None = None, *, transport=default_transport, sleep: Callable[[float], None] = time.sleep,
         monotonic: Callable[[], float] = time.monotonic, clock: Callable[[], dt.datetime] = utc_now, fetch=None) -> TickResult | None:
    """One round. It never raises: a failure is logged, and the next minute tries again."""
    env = os.environ if env is None else env
    redact = Redactor()
    try:
        settings = loop_config.load(env)
        if settings is None:
            return None
        cfg.load(env)  # the timer runs only while the settings of the app are valid
        options = {"sleep": sleep, **({"fetch": fetch} if fetch else {})}
        reader = Identity(env, **options)
        extras = wiring.build_extras(env, reader.token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
        if extras is None:
            return None
        check_client = Client(read_calls(settings.change_scopes), redact, transport=transport, sleep=sleep, monotonic=monotonic)
        reader_client = Client(allowed_calls(), redact, transport=transport, sleep=sleep, monotonic=monotonic)
        history = History(uuid.uuid4().hex, None, clock, redact)
        services = RunnerServices(extras.store, check_client, reader.token, wiring.approval_settings(settings),
                                  arm=Arm(reader_client, reader.token), clock=clock, sleep=sleep, emit=history.emit)
        result = runner.tick(services)
        _offer_cards(extras, redact)
        _remind(extras, clock, redact)
        if clock().minute % learning.SYNC_EVERY_MINUTES == 0:
            learning.sync(extras.store, clock(), arm=services.arm)  # the lessons of the plans that ended (cases/learning.py); it never raises
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


def card_posted(message, env: Mapping[str, str] | None = None, *, clock: Callable[[], dt.datetime] = utc_now) -> str:
    """What the trigger of the queue teams-posted calls: the flow says that it posted a card, and the app keeps which message it is (offers.record_posted). A store that cannot be written raises, so that
    the host tries again; a wrong message is refused and consumed."""
    from .offers import record_posted
    env = os.environ if env is None else env
    extras = wiring.build_extras(env, Identity(env).token, Redactor(), transport=default_transport, sleep=time.sleep, monotonic=time.monotonic, clock=clock)
    if extras is None:
        return "the loop is off"
    result = record_posted(message.get_body().decode("utf-8", "replace"), extras.store, extras.people, clock)
    LOG.info("a card that the flow posted: %s", result)
    return result
