"""The History: one line of the app's telemetry for each step, `meternaut_event ` and one compact JSON object.

The workbook (environment/cases/history.workbook.json) and tools/cases-check.py read these lines. A line never holds a secret, a key,
a token or an e-mail address: every line passes through the redactor, and a line that is too long is shortened, not split.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Callable

EVENT_PREFIX = "meternaut_event "
VERSION = 1
MAX_LINE = 8000
KINDS = ("run.started", "run.note", "lead.found", "case.started", "case.step", "case.result", "run.finished", "run.failed")
# The lines of the loop that follows a case: a plan, the change and its check, and a message. The tools that read a run's History know the kinds above only.
LOOP_KINDS = ("plan.created", "action.started", "action.finished", "action.verified", "mail.result", "tick.result")

LOGGER = logging.getLogger("meternaut.history")

# The texts of a line, in the order in which they are cut and, when that is not enough, dropped.
TEXTS = ("summary", "note", "reason", "recommendation")


def _fit(event: dict) -> str:
    """The line, shortened when it is too long: the objections go first, then each long text is cut to 200 characters, then the texts go."""
    line = _render(event)
    if len(line) <= MAX_LINE:
        return line
    event = dict(event)
    event.pop("objections", None)
    steps = [None] + [(key, True) for key in TEXTS] + [(key, False) for key in TEXTS]
    for step in steps:
        if step:
            key, cut = step
            if cut and isinstance(event.get(key), str) and len(event[key]) > 200:
                event[key] = event[key][:197] + "..."
            elif not cut:
                event.pop(key, None)
        line = _render(event)
        if len(line) <= MAX_LINE:
            return line
    return _render({k: event[k] for k in ("v", "ts", "runId", "requestId", "type") if k in event})


def _render(event: dict) -> str:
    return EVENT_PREFIX + json.dumps(event, separators=(",", ":"), ensure_ascii=True)


class History:
    def __init__(self, run_id: str, request_id: str | None, clock: Callable[[], dt.datetime], redact: Callable[[str], str],
                 logger: logging.Logger = LOGGER) -> None:
        self.run_id, self.request_id, self.clock, self.redact, self.logger = run_id, request_id, clock, redact, logger

    def emit(self, kind: str, **fields: object) -> dict:
        if kind not in KINDS + LOOP_KINDS:
            raise ValueError(f"{kind} is not a kind of History line")
        event = {"v": VERSION, "ts": self.clock().strftime("%Y-%m-%dT%H:%M:%SZ"), "runId": self.run_id, "requestId": self.request_id, "type": kind, **fields}
        self.logger.info(self.redact(_fit(event)))
        return event
