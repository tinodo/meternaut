"""The control message: one Watch now, started by the deployment workflow.

The message sits in the Storage queue of the app's host storage account. It carries the job name and a request id and nothing else, so it cannot choose a scope, a model, a
budget or a detector. A message that is older than 15 minutes (by the time the queue says that it was inserted), names another job or has no valid request id is refused and the
History says so; a refusal is an answer, so the message is consumed and does not go back to the queue. The Functions host base64-decodes the message text before it gets here.
A function that raises is tried again, five times in all (the first try included), and the message then goes to the poison queue of the same name with the suffix -poison
(https://learn.microsoft.com/azure/azure-functions/functions-bindings-storage-queue-trigger, "Poison messages").
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
from .study import run_study

JOB = "watch"
STUDY_JOB = "study"  # one Study now (cases/study.py), started by the same message: the job name and the request id, and nothing that chooses a scope, a model or a budget
STALE_SECONDS = 900
REQUEST_ID = re.compile(r"^[0-9a-f]{32}$")


def refuse(reason: str, request_id: str | None, clock: Callable[[], dt.datetime]) -> None:
    History(uuid.uuid4().hex, request_id, clock, Redactor()).emit("run.failed", reason=reason)


def handle_message(message, clock: Callable[[], dt.datetime] = utc_now, run: Callable[..., object] = run_watch, study: Callable[..., object] = run_study) -> bool:
    """Reads one control message and starts the run. Returns whether a run was started."""
    try:
        document = json.loads(message.get_body().decode("utf-8"))
    except (ValueError, AttributeError, UnicodeDecodeError):
        refuse("the control message is not JSON", None, clock)
        return False
    request_id = document.get("requestId") if isinstance(document, dict) else None
    if not isinstance(request_id, str) or not REQUEST_ID.match(request_id):
        refuse("the control message has no valid request id", None, clock)
        return False
    job = document.get("job")
    if job not in (JOB, STUDY_JOB):
        refuse(f"the control message names a job that the app does not know: {clean_text(document.get('job'), 40)}", request_id, clock)
        return False
    inserted = getattr(message, "insertion_time", None)
    if isinstance(inserted, dt.datetime):
        if inserted.tzinfo is None:
            inserted = inserted.replace(tzinfo=dt.timezone.utc)
        if (clock() - inserted).total_seconds() > STALE_SECONDS:
            refuse("stale control message", request_id, clock)
            return False
    (study if job == STUDY_JOB else run)("control", request_id)
    return True
