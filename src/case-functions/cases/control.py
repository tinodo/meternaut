"""The control event: one Watch now, started by the deployment workflow.

The event carries the job name and a request id and nothing else, so it cannot choose a scope, a model, a budget or a detector.
An event that is older than 15 minutes, names another job or has no valid request id is refused and the History says so.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from typing import Callable

from .events import History
from .redact import Redactor
from .roles import clean_text
from .run import run_watch, utc_now

JOB = "watch"
STALE_SECONDS = 900
REQUEST_ID = re.compile(r"^[0-9a-f]{32}$")


def refuse(reason: str, request_id: str | None, clock: Callable[[], dt.datetime]) -> None:
    History(uuid.uuid4().hex, request_id, clock, Redactor()).emit("run.failed", reason=reason)


def handle_event(event, clock: Callable[[], dt.datetime] = utc_now, run: Callable[..., object] = run_watch) -> bool:
    """Reads one control event and starts the run. Returns whether a run was started."""
    try:
        document = json.loads(event.get_body().decode("utf-8"))
    except (ValueError, AttributeError, UnicodeDecodeError):
        refuse("the control event is not JSON", None, clock)
        return False
    request_id = document.get("requestId") if isinstance(document, dict) else None
    if not isinstance(request_id, str) or not REQUEST_ID.match(request_id):
        refuse("the control event has no valid request id", None, clock)
        return False
    if document.get("job") != JOB:
        refuse(f"the control event names a job that the app does not know: {clean_text(document.get('job'), 40)}", request_id, clock)
        return False
    enqueued = getattr(event, "enqueued_time", None)
    if isinstance(enqueued, dt.datetime):
        if enqueued.tzinfo is None:
            enqueued = enqueued.replace(tzinfo=dt.timezone.utc)
        if (clock() - enqueued).total_seconds() > STALE_SECONDS:
            refuse("stale control event", request_id, clock)
            return False
    run("control", request_id)
    return True
