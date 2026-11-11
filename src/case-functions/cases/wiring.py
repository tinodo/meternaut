"""What the Watch, the console and the timer share when the loop is on: the store, the people, the approvals and the hook that sends a letter."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable, Mapping

from . import loop_config, people as people_mod
from .approvals import Approvals, ApprovalSettings
from .families.azure import Azure
from .http import Client
from .loop_config import LoopSettings
from .memory_store import utc_now
from .models import ActionRecord, CaseRecord, PlanRecord, RunRecord, Store
from .runner import read_calls
from .store import TableStore, table_calls


@dataclass
class Extras:
    """The parts of the loop that a Watch run uses. None of them exists when the loop is off."""

    settings: LoopSettings
    store: Store
    people: people_mod.People
    approvals: Approvals
    # Hooks that tell a person: all three are given the records and all may do nothing. They never raise.
    on_plan: Callable[[PlanRecord, CaseRecord], None] = lambda plan, case: None
    on_action: Callable[[ActionRecord, PlanRecord | None, CaseRecord | None], None] = lambda action, plan, case: None
    on_run: Callable[[RunRecord], None] = lambda run: None
    # The letter of a trip of the agent harness or of the drift check (cases/harness.py, cases/drift.py): given the code of the reason and a plain detail, it tells the owner once.
    on_alert: Callable[[str, str], None] = lambda code, detail: None
    # What the timer calls every minute for the letters that a person's quiet hours held back and that nothing else offers again (cases/notify.waiting_hook). It never raises.
    on_tick: Callable[[], None] = lambda: None

    def approvers(self) -> tuple[str, ...]:
        return tuple(p.oid for p in self.people.with_role("approver"))


def approval_settings(settings: LoopSettings) -> ApprovalSettings:
    return ApprovalSettings(change_scopes=settings.change_scopes, planted_tag=settings.planted_tag, ttl_hours=settings.plan_ttl_hours)


def build_store(settings: LoopSettings, token: Callable[[str], str], redact: Callable[[str], str], *, transport, sleep, monotonic,
                clock: Callable[[], dt.datetime] = utc_now) -> TableStore:
    client = Client(table_calls(settings.store_account), redact, transport=transport, sleep=sleep, monotonic=monotonic)
    return TableStore(client, token, settings.store_account, clock=clock)


def build_extras(env: Mapping[str, str], token: Callable[[str], str], redact: Callable[[str], str], *, transport, sleep, monotonic,
                 clock: Callable[[], dt.datetime] = utc_now) -> Extras | None:
    """None when the loop is not configured. Raises LoopConfigError or PeopleError when it is configured wrongly: a half loop is not run."""
    settings = loop_config.load(env)
    if settings is None:
        return None
    people = people_mod.load(env)
    store = build_store(settings, token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
    # The reader of the plans: the Watch's own token and a list of calls that holds reads only, and only in the resource groups of the change scopes. A family reads the machine, the sizes
    # or the disk that its plan is about with it, never anything else.
    reader = Azure(Client(read_calls(settings.change_scopes), redact, transport=transport, sleep=sleep, monotonic=monotonic), token)
    extras = Extras(settings, store, people, Approvals(store, approval_settings(settings), clock, reader=reader))
    if settings.mail_sender:
        from .notify import alert_hook, hooks, waiting_hook  # imported only when a sender is set
        extras.on_plan, extras.on_action, extras.on_run = hooks(env, settings, store, people, token, redact, transport=transport, sleep=sleep,
                                                                monotonic=monotonic, clock=clock)
        extras.on_alert = alert_hook(settings, store, people, token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
        extras.on_tick = waiting_hook(settings, store, people, token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
    return extras
