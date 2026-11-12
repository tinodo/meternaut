"""The look that a page takes before it offers Approve: the checks that the runner makes right before a change, made now with the app's own reader.

The runner re-checks everything right before it acts (cases/runner.py: the family's `recheck`, with the approver's own token), and when a check refuses, it changes nothing. That is the guard,
and it stays the guard. But a person who is offered a button that the guard will then refuse has signed in to Azure for nothing, and has been told by a page that a change can be made
when it cannot. So a page asks this module first, and offers Approve only when the answer is not "refused" (models.Readiness).

The look is the family's own `recheck`, not a copy of it: the gates (the scope, the planted tag and the planted list), the state that the family wants, a person's do-not-touch note and the
management locks are read and judged by the same code that stands behind the change. It makes no call but reads. The reader is the app's own identity with a list of calls that holds reads
only (runner.read_calls), the one that the Watch and the timer use, so the page gains no right to change anything (AGENTS.md rule 29). The token of the approver is not here: the approver
has not signed in to Azure yet when the page is shown.

A look has a time limit, because a page waits for it. What it cannot read it does not judge: a read that fails is `unknown` and not `refused`, because the app's reader may see less than the
approver does, and the runner looks again with the approver's own rights right before it acts. The answer is advice for a page, never a decision: no record is written here.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable

from .approvals import ApprovalSettings
from .families import digest as plan_digest
from .families import registry
from .families.azure import Azure
from .families.base import Env, Stop
from .http import HttpError, Refused
from .memory_store import utc_now
from .models import ADVISE, READY, REFUSED, UNKNOWN, PlanRecord, Readiness, Store, StoreError

# The most seconds that one look may take (the deadline of the client that it reads with): no call starts after it, and no pause is taken that would end after it.
LOOK_SECONDS = 10


class Precheck:
    """The Checker of the pages (models.Checker). `reader` makes the reader for one look: the app's own identity, a client whose list of calls holds reads only, and a deadline of its own."""

    def __init__(self, store: Store, settings: ApprovalSettings, reader: Callable[[], Azure], clock: Callable[[], dt.datetime] = utc_now) -> None:
        self.store, self.settings, self.reader, self.clock = store, settings, reader, clock

    def check(self, plan: PlanRecord) -> Readiness:
        """What a look at the resource says about the change of this plan. Only the plan of a change that is open is looked at: for any other plan the answer is `ready`, and no call is made."""
        if plan.state != "open" or plan.family == ADVISE:
            return Readiness(READY)
        family = registry.get(plan.family)
        if family is None:
            return Readiness(REFUSED, "the request names a change that Meternaut does not make")
        problem = plan_digest.problem(plan, plan.digest)
        if problem:
            return Readiness(REFUSED, problem)
        try:
            _, resource = family.recheck(Env(self.reader(), self.settings.gates, self.store.do_not_touch, self.clock), plan)
        except Stop as stop:
            # A refusal of Azure to read (the reader's, not the approver's) and a read that failed say nothing about the resource: they are not "refused".
            return Readiness(UNKNOWN) if stop.unread or stop.kind != "stopped" else Readiness(REFUSED, str(stop))
        except (HttpError, Refused, StoreError):
            return Readiness(UNKNOWN)
        except Exception:  # noqa: BLE001 (a look that fails in any other way is a look that was not made: the page is shown without it)
            return Readiness(UNKNOWN)
        if resource is None and not family.deletes:
            return Readiness(REFUSED, "the resource does not exist any more")
        return Readiness(READY)
