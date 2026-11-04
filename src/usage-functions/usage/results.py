"""The result line that every job run writes to the log.

The deployment workflow reads this line from the telemetry. Its prefix and its twelve keys are a contract: change them
only together with tools/recording-check.py. The line holds counts, ids and timestamps; never the content of an event.
"""
import json
from dataclasses import dataclass

RESULT_PREFIX = "usage_job_result "
TIMER = "timer"
CONTROL = "control"
ERROR_MAX_LENGTH = 300


@dataclass(frozen=True)
class JobResult:
    job: str
    request_id: str | None
    trigger: str
    ok: bool
    first_run: bool
    window_from: str | None
    window_to: str | None
    rows: int
    written: int
    container_count: int | None
    marker: str | None
    error: str | None

    def to_payload(self) -> dict[str, object]:
        return {
            "job": self.job,
            "requestId": self.request_id,
            "trigger": self.trigger,
            "ok": self.ok,
            "firstRun": self.first_run,
            "from": self.window_from,
            "to": self.window_to,
            "rows": self.rows,
            "written": self.written,
            "containerCount": self.container_count,
            "marker": self.marker,
            "error": self.error,
        }

    def to_line(self) -> str:
        return RESULT_PREFIX + json.dumps(self.to_payload(), separators=(",", ":"))


def describe_error(exc: BaseException) -> str:
    """The class name and the first line of the message, at most ERROR_MAX_LENGTH characters of it."""
    message = str(exc).strip()
    first_line = message.splitlines()[0] if message else ""
    return f"{type(exc).__name__}: {first_line[:ERROR_MAX_LENGTH]}"
