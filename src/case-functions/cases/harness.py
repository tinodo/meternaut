"""The agent harness: what surrounds an agent run, in one place that a person can read.

An agent is a model with instructions and tools. This module is everything that is not the agent: the lock that says what each agent may be, the brakes, the budgets, the guards on its
tool calls and the telemetry. Nothing here is a model, and nothing in it can be talked out of a decision. It works for both agents of the investigation (cases/agents.py), and it is
read as one list:

| Around the agent            | What it does                                                                                                                                          |
|-----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| The lock                    | `agents.lock.json` holds the model alias, the hash of the instructions, of the tool schemas and of the code of each tool. A definition in the project |
|                             | that differs is refused, never repaired in silence, and trips the brake. The code that is running has to equal the lock too.                            |
| The switches                | `all` and `investigation` are read before the agent is made ready and before every request to its model. A switch that cannot be read is pulled.       |
| The budgets                 | Tool calls, seconds and tokens, kept in one place (Budget) and reported on the trace line of every run. The tokens are a brake here: a run that has   |
|                             | used them is stopped.                                                                                                                                  |
| The guard on the tool calls | A tool that is not on the list, arguments that are not of the shape that the tool's schema declares, and the same call again and again are refused.   |
| The answer guards           | A handle that no tool returned, an answer that code cannot read and an agent that ends with no answer count as failures of the run.                    |
| The trips                   | Three refusals or guard failures in one run, a breach of the token budget and a stored definition that differs pull the switch `investigation` and     |
|                             | send one letter. Only that switch: it is narrow, and a person releases it.                                                                              |
| The trace                   | One line `harness.run` for every run and `harness.trip` for every trip, with plain codes and numbers and no text of an estate (the app has no          |
|                             | telemetry library: the host ships these lines to Application Insights, where the alert rules read them by their first word).                          |

What none of it stops: a model that is misled into a proposal that code and a person then accept, a tool that behaves differently behind an unchanged schema and unchanged code (the
lock holds the hash of the code that runs it, so that this is noticed when the code changes, not when the data does), and a person who approves what they should not.

The harness is built by cases/run.py for the client of the Foundry project that the run makes, and cases/investigate.py uses it for both agents. A test that hands the run a client of its
own hands it a harness too (or none).
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import logging
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from . import alerts, drift_rules, lockfile, release, switches
from .foundry import NO_TEXT, AgentRun, AgentSpec, FoundryError, ToolHandler, definition_of
from .memory_store import stamp
from .models import SwitchRecord

LOGGER = logging.getLogger("meternaut.harness")
RUN = "harness.run"
TRIP = "harness.trip"
DRIFT_PREFIXES = {"PASS": "drift.pass", "FAIL": "drift.fail", "UNKNOWN": "drift.unknown"}
PACKAGE_SETTING = "PACKAGE_SHA256"  # the app setting that the deployment sets to the digest of the files that it ships (tools/package-digest.py)
SWITCH = "investigation"
STOPPING = ("all", SWITCH)
BY = "the agent harness"
# The starting values of the limits, written here before they were measured. The fourth real run of the Investigator (2026-11-08) used 17 tool calls and about 169,000 tokens in all (the
# Investigator and the Skeptic); a run is stopped at about three and a half times that, which no run of the loop reaches and a loop in a model does.
REPEAT_LIMIT = 2  # the same call (the same tool, the same arguments) may be made twice; the third is refused
TRIP_LIMIT = 3  # refusals and guard failures in one run
SKEPTIC_TOKENS = 100_000  # the Skeptic reads one input of at most 30,000 characters and answers once
MAX_ARGUMENT_DEPTH = 8
KEY = re.compile(r"[A-Za-z][A-Za-z0-9]{0,31}")
COMMIT = re.compile(r"[0-9a-f]{7,40}")
# What the model is told when its call is refused: fixed words, the same for every call.
REFUSALS = {"tool": '{"error":"not-allowed"}', "arguments": '{"error":"bad-arguments"}', "repeat": '{"error":"repeat"}'}


class HarnessRefused(FoundryError):
    """The harness did not let the agent run. `reason` is a code of a closed list; the text says the same in plain words and holds no text of the definition."""

    reason: str = ""


def _refused(reason: str, words: str) -> HarnessRefused:
    error = HarnessRefused(f"the harness refused the run: {words}")
    error.reason = reason
    return error


# -- the trace -------------------------------------------------------------------------------------------------------------------------------------

def _value(value: object, limit: int = 300) -> object:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 3) if math.isfinite(value) else None
    if isinstance(value, (list, tuple)):
        return [_value(item, 80) for item in list(value)[:20]]
    return alerts.plain(value, limit)


def trace(prefix: str, payload: Mapping[str, object], redact: Callable[[str], str] = str, *, level: int = logging.INFO, logger: logging.Logger = LOGGER) -> str:
    """One line of the app's telemetry: a prefix that an alert rule reads, a space and one compact JSON object. Every value is a number, a flag or a plain short text (letters, digits and a
    few marks): a text of an estate cannot get into it, and a key that is not a plain word is left out."""
    clean = {key: _value(value) for key, value in payload.items() if isinstance(key, str) and KEY.fullmatch(key)}
    line = redact(f"{prefix} {json.dumps(clean, separators=(',', ':'), ensure_ascii=True)}")
    logger.log(level, line)
    return line


@functools.lru_cache(maxsize=1)
def package_digest() -> tuple[str, int]:
    """The digest of the app's own files (cases/release.py), made once per process. ("", 0) when the folder cannot be read."""
    try:
        return release.digest(release.app_folder())
    except release.ReleaseError:
        return "", 0


def build_of(env: Mapping[str, str] | None) -> str:
    """The commit that the package was built from (the app setting BUILD_COMMIT, which the deployment sets), as at most 12 characters, or "unknown"."""
    value = ((env or {}).get("BUILD_COMMIT") or "").strip().lower()
    return value[:12] if COMMIT.fullmatch(value) else "unknown"


def announce(env: Mapping[str, str] | None = None, redact: Callable[[str], str] = str) -> dict:
    """Says once, when the app starts, which package is running: the digest of its files, the commit that it was built from (BUILD_COMMIT, an app setting that the deployment sets; the
    environment of the process when no environment is given) and whether the digest is the released one: `release` is PASS when it equals PACKAGE_SHA256, FAIL when it differs (a warning) and
    UNKNOWN when the setting is not there (the same judgement as the drift control A-RELEASE, which holds it every day). It never raises."""
    try:
        digest, count = package_digest()
        environment = os.environ if env is None else env
        build = build_of(environment)
        released = drift_rules.judge_release(digest, count, environment.get(PACKAGE_SETTING, ""), build).state
        payload = {"event": "startup", "package": digest[:12] or "unknown", "files": count, "build": build, "release": released}
        trace(RUN, payload, redact, level=logging.WARNING if released == drift_rules.FAIL else logging.INFO)
        return payload
    except Exception:  # noqa: BLE001 (a line of the telemetry never stops the app)
        return {}


# -- the guard on a tool call ----------------------------------------------------------------------------------------------------------------------

def _is(kind: object, value: object) -> bool:
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return (isinstance(value, int) and not isinstance(value, bool)) or (isinstance(value, float) and math.isfinite(value) and value.is_integer())
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and (not isinstance(value, float) or math.isfinite(value))
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    return False


def conforms(schema: object, value: object, depth: int = 0) -> bool:
    """Whether a value has the shape that a JSON schema declares: its type, the keys of an object (no key that the schema does not declare), a value from an enum, the bounds of a number
    and of an array. A pattern of a string and the `required` list are not read: the tool checks the values and takes an optional argument as null when it is left out, so a call that the tool
    would answer is not refused here. The shape is what the harness holds to the schema; what the arguments mean is the tool's."""
    if depth > MAX_ARGUMENT_DEPTH or not isinstance(schema, dict):
        return False
    kind = schema.get("type")
    kinds = kind if isinstance(kind, list) else [kind] if kind is not None else None
    if kinds is not None and not any(_is(k, value) for k in kinds):
        return False
    options = schema.get("enum")
    if isinstance(options, list) and not any(value == option and type(value) is type(option) for option in options):
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(schema.get("minimum"), (int, float)) and value < schema["minimum"]:
            return False
        if isinstance(schema.get("maximum"), (int, float)) and value > schema["maximum"]:
            return False
    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            return False
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            return False
        if isinstance(schema.get("items"), dict) and not all(conforms(schema["items"], item, depth + 1) for item in value):
            return False
    if isinstance(value, dict):
        declared = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        if schema.get("additionalProperties") is False and set(value) - set(declared):
            return False
        if not all(conforms(declared[key], item, depth + 1) for key, item in value.items() if key in declared):
            return False
    return True


class ToolGuard:
    """The tools that an agent may call, their argument schemas and the calls so far. `check` gives the code of a refusal, or None when the call may go to the tool."""

    def __init__(self, tools: tuple, repeat_limit: int = REPEAT_LIMIT) -> None:
        self.schemas = {tool.name: tool.parameters for tool in tools}
        self.repeat_limit = repeat_limit
        self.seen: Counter[tuple[str, str]] = Counter()

    def check(self, name: object, arguments: object) -> str | None:
        schema = self.schemas.get(name) if isinstance(name, str) else None
        if schema is None:
            return "tool"
        if not isinstance(arguments, dict) or not conforms(schema, arguments):
            return "arguments"
        try:
            key = (name, lockfile.canonical(arguments))
        except (TypeError, ValueError, RecursionError):
            return "arguments"
        self.seen[key] += 1
        return "repeat" if self.seen[key] > self.repeat_limit else None


# -- the budgets -----------------------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Budget:
    """The limits of one agent run, in one place. The calls and the seconds are passed to the Foundry loop (which enforces them and answers a call beyond the budget); the tokens are a
    brake of the harness; the rest says when a run counts as misbehaving."""

    tool_calls: int
    tokens: int
    skeptic_tokens: int = SKEPTIC_TOKENS
    repeat_limit: int = REPEAT_LIMIT
    trip_limit: int = TRIP_LIMIT

    @classmethod
    def of(cls, settings: object) -> "Budget":
        return cls(tool_calls=int(getattr(settings, "investigate_max_calls")), tokens=int(getattr(settings, "investigate_max_tokens")))

    def tokens_for(self, spec: AgentSpec) -> int:
        return self.tokens if spec.tools else self.skeptic_tokens


# -- the brake -------------------------------------------------------------------------------------------------------------------------------------

class Brake:
    """The one way that the harness and the drift check stop the agents: the switch `investigation` is pulled, and one letter goes to the owner. It writes that one switch and nothing else,
    only ever to pulled, and does nothing when the switch is pulled already, so a cause that stays does not send a letter every time it is seen."""

    def __init__(self, store: object, alert: Callable[[str, str], None] | None, clock: Callable[[], dt.datetime], redact: Callable[[str], str] = str) -> None:
        self.store, self.alert, self.clock, self.redact = store, alert, clock, redact

    def pull(self, code: str, detail: str = "") -> bool:
        """Pulls the switch for a reason (a code of alerts.REASONS), tells the owner once and writes the line `harness.trip`. True when this call pulled it."""
        outcome = "pulled"
        try:
            if self.store is None:
                outcome = "no-store"
            elif self.store.switch_get(SWITCH).paused:  # type: ignore[attr-defined]
                outcome = "already"
            else:
                self.store.switch_put(SwitchRecord(name=SWITCH, paused=True, by=BY, at=stamp(self.clock()), reason=alerts.switch_reason(code)))  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 (a switch that cannot be read is pulled for every reader already)
            outcome = "unreadable"
        trace(TRIP, {"reason": code, "switch": SWITCH, "outcome": outcome, "detail": detail}, self.redact, level=logging.WARNING)
        if outcome == "pulled" and self.alert is not None:
            try:
                self.alert(code, detail)
            except Exception:  # noqa: BLE001 (a letter that cannot be sent never undoes a trip)
                LOGGER.error(self.redact("the letter of a trip could not be sent"))
        return outcome == "pulled"


# -- one run ---------------------------------------------------------------------------------------------------------------------------------------

@dataclass
class RunRecord:
    """What happened around one agent run, as the harness saw it. It becomes one line `harness.run`."""

    agent: str
    definition: str
    version: str = ""
    began: float = 0.0
    limit: int = 0  # the token budget of this run
    tokens: int = 0
    tool_calls: int = 0
    refused: int = 0  # calls that the harness refused
    budget_refused: int = 0  # calls that the loop refused after the budget of calls or the time was used up (they are no failure of the agent's)
    guard_failures: int = 0
    seconds: int = 0
    outcome: str = "idle"
    reason: str = ""
    breach: str = ""
    codes: list[str] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    closed: bool = False

    def failures(self) -> int:
        return self.refused + self.guard_failures


class Harness:
    """Everything around the agents of one Watch. See the module's text for the list."""

    def __init__(self, *, foundry: object, store: object, lock: lockfile.Lock | None, lock_error: str, budget: Budget, brake: Brake, clock: Callable[[], dt.datetime],
                 monotonic: Callable[[], float], redact: Callable[[str], str] = str, env: Mapping[str, str] | None = None,
                 digests: Callable[[], tuple[Mapping[str, str], str]] | None = None) -> None:
        self.foundry, self.store, self.lock, self.lock_error, self.budget, self.brake = foundry, store, lock, lock_error, budget, brake
        self.clock, self.monotonic, self.redact, self.env = clock, monotonic, redact, env or {}
        self.digests = digests or code_digests
        self.records: list[RunRecord] = []
        self._digests: tuple[Mapping[str, str], str] | None = None

    # -- before a run ----------------------------------------------------------------------------------------------------------------------------
    def ensure(self, spec: AgentSpec) -> str:
        """Makes the agent ready for a run, or refuses it: HarnessRefused when the lock, the switches or the stored definition say no, and the FoundryError of the service when it fails.
        Returns the reference that the run uses, `name:version`. The agent is made, or a new version of it, only from a definition that equals the lock."""
        record = RunRecord(agent=spec.name, definition=(self.lock.definition_sha256(spec.name)[:8] if self.lock else ""), began=self.monotonic())
        self.records.append(record)
        try:
            entry = self._admit(spec)
            reference = self.foundry.ensure_agent(spec)  # type: ignore[attr-defined]
            record.version = reference.partition(":")[2]
            self._verify_stored(spec, entry, record)
            return reference
        except HarnessRefused as refusal:
            record.outcome, record.reason = "refused", refusal.reason
            raise
        except FoundryError:
            record.outcome, record.reason = "failed", "service"
            raise

    def _admit(self, spec: AgentSpec) -> Mapping:
        if self.lock is None:
            raise _refused("lock", f"the lock of the agents cannot be used ({alerts.plain(self.lock_error, 120)})")
        entry = self.lock.entry(spec.name)
        if entry is None:
            raise _refused("lock", "the lock does not list this agent")
        if self.store is None:
            raise _refused("no-store", "no store holds the switches, so they count as pulled")
        if switches.pulled(self.store, *STOPPING):  # type: ignore[arg-type]
            raise _refused("switch", "the switch investigation or the switch all is pulled, or cannot be read")
        problems = self.code_problems(spec, entry)
        if problems:
            raise _refused("lock-differs", "the code that would run is not what the lock says: " + "; ".join(problems[:3]))
        return entry

    def code_problems(self, spec: AgentSpec, entry: Mapping) -> list[str]:
        """How the code that is about to run differs from the lock: the definition that it would send, the schemas and the code of its tools, and the module of the tools."""
        assert self.lock is not None
        facts = lockfile.facts_of(definition_of(spec), self.lock.ignored)
        problems = [difference.what for difference in lockfile.compare(entry, facts)]
        if self._digests is None:
            self._digests = self.digests()
        implementations, module = self._digests
        for tool in spec.tools:
            locked = self.lock.tools.get(tool.name)
            if locked is None:
                problems.append(f"tool {tool.name} is not in the lock")
                continue
            if lockfile.digest(lockfile.schema_of({"name": tool.name, "description": tool.description, "parameters": tool.parameters})) != locked["schemaSha256"]:
                problems.append(f"the schema of tool {tool.name} changed")
            if implementations.get(tool.name, "") != locked["implementationSha256"]:
                problems.append(f"the code of tool {tool.name} changed")
        if spec.tools and module != self.lock.toolbox_sha256:
            problems.append("the module of the tools changed")
        return problems

    def _verify_stored(self, spec: AgentSpec, entry: Mapping, record: RunRecord) -> None:
        """Reads the agent as the project stores it, after it was made ready, and holds it against the lock. A stored definition that differs is refused and trips the brake: somebody
        changed an agent outside a release, or the version that carries the hash of this app's definition holds another one."""
        assert self.lock is not None
        name, version = spec.name, record.version
        try:
            latest = self.foundry.read_agent(name)  # type: ignore[attr-defined]
        except FoundryError as error:
            raise _refused("stored-unreadable", f"the stored definition cannot be read ({alerts.plain(error, 120)})") from None
        if latest is None:
            raise _refused("stored-missing", "the agent is not in the project after it was made")
        if str(latest.get("version")) != version:
            raise _refused("version-moved", "a newer version of the agent appeared while the run was being prepared")
        definition = latest.get("definition") if isinstance(latest.get("definition"), dict) else {}
        differences = lockfile.compare(entry, lockfile.facts_of(definition, self.lock.ignored))
        certain = [difference for difference in differences if difference.certain]
        record.options = [difference.code for difference in differences if not difference.certain]
        if certain:
            controls = sorted({difference.control for difference in certain})
            self.brake.pull("definition", f"{spec.name}: " + ", ".join(controls))
            raise _refused("definition", "the stored definition differs from the lock (" + ", ".join(controls) + ")")

    # -- during a run ----------------------------------------------------------------------------------------------------------------------------
    def run(self, reference: str, spec: AgentSpec, user_input: str, handler: ToolHandler | None, *, max_calls: int | None = None, max_seconds: float) -> AgentRun:
        """Runs the agent through the Foundry loop with the guard on its tool calls and the brake before each request to its model. The budget of tool calls is the harness's (Budget)
        unless the caller gives one: the Skeptic has no tools, so its caller gives 0."""
        record = self._record_of(spec)
        guard = ToolGuard(spec.tools, self.budget.repeat_limit)
        limit = record.limit = self.budget.tokens_for(spec)
        calls = self.budget.tool_calls if max_calls is None else max_calls

        def handle(name: str, arguments: dict) -> str:
            code = guard.check(name, arguments)
            if code is not None or handler is None:
                record.refused += 1
                record.codes.append(code or "tool")
                return REFUSALS[code or "tool"]
            return handler(name, arguments)

        def stop(progress: AgentRun) -> str | None:
            record.tokens = progress.input_tokens + progress.output_tokens
            if switches.pulled(self.store, *STOPPING):  # type: ignore[arg-type]
                record.breach = record.breach or "switch"
                return "the switch investigation or the switch all is pulled, or cannot be read"
            if record.tokens >= limit:
                record.breach = "tokens"
                return "the token budget of the run is used up"
            if record.failures() >= self.budget.trip_limit:
                record.breach = "refusals"
                return f"{self.budget.trip_limit} refusals or guard failures in this run"
            return None

        try:
            result = self.foundry.run(reference, user_input, handle, max_calls=calls, max_seconds=max_seconds, stop=stop)  # type: ignore[attr-defined]
        except FoundryError as error:
            partial = getattr(error, "partial", None)
            if partial is not None:
                self._count(record, partial)
            text = str(error)
            record.seconds = int(self.monotonic() - record.began)
            if "stopped by the harness" in text:
                record.outcome = "stopped"
                record.reason = record.breach or "stopped"
                refusal = _refused(record.reason, text.split("stopped by the harness: ", 1)[-1])
                refusal.partial = partial
                raise refusal from None
            if text.endswith(NO_TEXT):
                record.outcome, record.reason = "failed", "no-answer"
                record.guard_failures += 1
                record.codes.append("no-answer")
            else:
                record.outcome, record.reason = "failed", "service"
            raise
        except Exception:
            record.outcome, record.reason = "failed", "error"
            record.seconds = int(self.monotonic() - record.began)
            raise
        self._count(record, result)
        record.outcome = "ok"
        record.seconds = int(self.monotonic() - record.began)
        if record.tokens > limit:
            record.breach = "tokens"
        return result

    def _count(self, record: RunRecord, progress: AgentRun) -> None:
        record.tokens = progress.input_tokens + progress.output_tokens
        made = [call for call in progress.calls if isinstance(call, dict) and not call.get("refused")]
        record.tool_calls = len(made) - record.refused
        record.budget_refused = len(progress.calls) - len(made)

    def _record_of(self, spec: AgentSpec) -> RunRecord:
        for record in reversed(self.records):
            if record.agent == spec.name and record.outcome in ("idle", "ok"):
                return record
        record = RunRecord(agent=spec.name, definition=(self.lock.definition_sha256(spec.name)[:8] if self.lock else ""), began=self.monotonic())
        self.records.append(record)
        return record

    # -- after a run -----------------------------------------------------------------------------------------------------------------------------
    def guard_failed(self, agent: str, code: str) -> None:
        """An answer that code rejected: a handle that no tool returned (`unknown-handle`) or an answer that code cannot read (`unreadable`). It counts toward the trip of that run."""
        for record in reversed(self.records):
            if record.agent == agent and record.outcome in ("ok", "failed", "stopped"):
                record.guard_failures += 1
                record.codes.append(code)
                if code == "unreadable" and record.outcome == "ok":
                    record.outcome, record.reason = "answer-rejected", "unreadable"
                return

    def close(self) -> None:
        """Writes the line `harness.run` for every run that was refused or ran, and pulls the brake for a run that breached the token budget or had too many refusals and guard failures. It
        never raises, and it is safe to call twice."""
        for record in self.records:
            if record.closed:
                continue
            record.closed = True
            try:
                self._finish(record)
            except Exception:  # noqa: BLE001 (the telemetry of a run never stops the Watch)
                LOGGER.error(self.redact("the line of a run could not be written"))

    def _finish(self, record: RunRecord) -> None:
        if record.outcome == "idle":
            return
        digest, _ = package_digest()
        trace(RUN, {
            "agent": record.agent, "version": record.version, "definition": record.definition, "lock": self.lock.sha256[:8] if self.lock else "", "package": digest[:12] or "unknown",
            "build": build_of(self.env), "tokens": record.tokens, "toolCalls": record.tool_calls, "refused": record.refused, "budgetRefused": record.budget_refused,
            "guardFailures": record.guard_failures, "seconds": record.seconds, "outcome": record.outcome, "reason": record.reason,
            "codes": sorted(set(record.codes)), "options": sorted(set(record.options))}, self.redact)
        if record.breach == "tokens":
            self.brake.pull("tokens", f"{record.agent}: {record.tokens} tokens against a budget of {record.limit}")
        elif record.failures() >= self.budget.trip_limit:
            self.brake.pull("refusals", f"{record.agent}: {record.refused} refused calls, {record.guard_failures} guard failures")


def code_digests() -> tuple[Mapping[str, str], str]:
    """The digests of the code of the tools that this app has: of each tool's method and of the module of the tools. They are held against the lock before an agent is made ready."""
    from . import toolbox

    names = [tool.name for tool in toolbox.SPECS]
    module = Path(toolbox.__file__).read_text(encoding="utf-8")
    return lockfile.implementation_digests(toolbox.Toolbox, names), lockfile.source_digest(module)


def build(settings: object, foundry: object, extras: object | None, *, env: Mapping[str, str] | None = None, clock: Callable[[], dt.datetime], monotonic: Callable[[], float],
          redact: Callable[[str], str] = str, lock_path: Path | None = None) -> Harness:
    """The harness of one Watch. A lock that cannot be read makes a harness that refuses every run and says why: no lock, no agent."""
    try:
        lock, problem = lockfile.load(lock_path), ""
    except lockfile.LockError as error:
        lock, problem = None, str(error)
    store = getattr(extras, "store", None)
    alert = getattr(extras, "on_alert", None)
    return Harness(foundry=foundry, store=store, lock=lock, lock_error=problem, budget=Budget.of(settings), brake=Brake(store, alert, clock, redact), clock=clock,
                   monotonic=monotonic, redact=redact, env=env)
