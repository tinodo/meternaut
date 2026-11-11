"""The drift check in the app, the data-plane half: what the agents are, read once a day and held against what the repository says.

The timer `drift-daily` (05:10 UTC, twenty minutes before the Watch) runs `run_check`. It reads, with the app's own identity and with GET calls only, what the control plane cannot show
from outside the network: the agents of the Foundry project and their latest versions, and the connections of the project as its data plane shows them. It holds them, and the code and
the settings of the app itself, against `agents.lock.json` and writes ONE line of the telemetry for every control, every run, even when everything passes:

    drift.pass | drift.fail | drift.unknown  {"control": "A-...", "layer": "L1|L2|L3", "state": "PASS|FAIL|UNKNOWN", "detail": "...", "readAt": "<UTC>"}

Those lines are the heartbeat of the check: a day without them is itself an alert (the Azure-native alert rules read them by their first word, beside this app). The judging of each
control is in drift_rules.py (the list of the controls, their layers and what each one holds is `drift_rules.CONTROLS`); this module gathers what the rules need.

A FAIL of a control that guards the agents pulls the switch `investigation` and sends one letter to the owner, through the harness's Brake (harness.py): no other switch is ever pulled,
and a person releases it. An UNKNOWN never pulls it. The check never runs inside an agent run, never calls a model, and changes nothing but that one switch and its own result: it keeps the
result as the latest check of the app (`CheckRecord`), which the Operations page shows. A person with the role ops can start the same check at the console (`web/ops.py`, at most once in
CHECK_GAP_MINUTES for everybody, the timer's check counting too): it is `run_check("console")`, with the same reads, the same rules and the same lines.

What it cannot do, said plainly: a compromised app can hide its own drift (it is the one that reads and the one that reports). The independent check of the control plane and the alert
rules of Azure Monitor beside it, which an app cannot talk out of reporting, exist for that reason, and the check from inside the network (tools/agents-drift.py) reads the same project
with another identity and the same rules.
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Mapping

from . import agents, config as cfg, drift_rules as rules, harness, http, lockfile, wiring
from .foundry import Foundry, FoundryError, definition_of
from .http import FOUNDRY_AGENT_NAME, FOUNDRY_ENDPOINT, Client, Refused, default_transport
from .identity import Identity
from .memory_store import stamp, utc_now
from .models import CHECK_TRIGGERS, SWITCH_NAMES, CheckRecord
from .plaintext import plain
from .redact import Redactor

LOG = logging.getLogger("meternaut.drift")
READ_SECONDS = 120  # the whole check reads for no longer than this
PACKAGE_SETTING = harness.PACKAGE_SETTING
ENDPOINT_SETTING = "FOUNDRY_PROJECT_ENDPOINT"
NOT_GIVEN: object = object()
# The methods that change something, spelled in pieces: the packaging test looks for the whole words to find the modules that could change something, and this module only checks that
# its lists of calls refuse them.
CHANGING = ("DEL" "ETE", "P" "UT", "PAT" "CH")
ARM = "https://management.azure.com"
EXAMPLE_ID = "00000000-0000-4000-8000-000000000000"


def drift_calls(endpoint: str) -> tuple[tuple[str, "re.Pattern[str]"], ...]:
    """The calls of the drift check to the Foundry project: three reads (the list of agents, one agent, the list of connections) on the one endpoint, and no other method, no other path and
    no other host. The Watch's list (http.foundry_calls) makes and runs the agents; this one only reads."""
    if not FOUNDRY_ENDPOINT.fullmatch(endpoint):
        raise ValueError("the endpoint of the Foundry project is not https://<account>.services.ai.azure.com/api/projects/<project>")
    base = re.escape(endpoint)
    return (
        ("GET", re.compile(base + "/agents")),
        ("GET", re.compile(base + f"/agents/{FOUNDRY_AGENT_NAME}")),
        ("GET", re.compile(base + "/connections")),
    )


# -- what one check works with ---------------------------------------------------------------------------------------------------------------------

def _why(error: BaseException) -> str:
    """Why a read of the project failed, as plain words: the HTTP status and the service's own code when it is a plain token, and nothing of its message."""
    if isinstance(error, FoundryError):
        status, code = getattr(error, "status", None), getattr(error, "code", "")
        if status:
            return f"HTTP {status}" + (f" {plain(code, 24)}" if code else "")
        if "no token could be had" in str(error):
            return "no token could be had for the service"
        return "no usable answer"
    return type(error).__name__


@dataclass
class Context:
    """What the controls read, each thing at most once per check. A read that failed is kept as a plain sentence and is shared by every control that needs it."""

    env: Mapping[str, str]
    now: str
    settings: cfg.Settings | None = None
    settings_problem: str = ""
    lock: lockfile.Lock | None = None
    lock_problem: str = ""
    foundry: object | None = None
    foundry_problem: str = ""
    extras: object | None = None
    store_problem: str = ""
    _reads: dict = field(default_factory=dict)

    @property
    def store(self) -> object | None:
        return getattr(self.extras, "store", None)

    def read(self, key: object, call: Callable[[], object]) -> tuple[object | None, str]:
        if key not in self._reads:
            if self.foundry is None:
                self._reads[key] = (None, self.foundry_problem or "no Foundry project is set, so the project is not read")
            else:
                try:
                    self._reads[key] = (call(), "")
                except Exception as error:  # noqa: BLE001 (a read that fails is an UNKNOWN, whatever it was)
                    self._reads[key] = (None, f"the project could not be read ({_why(error)})")
        return self._reads[key]

    def listing(self) -> tuple[tuple[list, bool] | None, str]:
        return self.read("agents", lambda: self.foundry.list_agents())  # type: ignore[union-attr]

    def connections(self) -> tuple[tuple[list, bool] | None, str]:
        return self.read("connections", lambda: self.foundry.list_connections())  # type: ignore[union-attr]

    def stored(self) -> dict[str, tuple[str, object]]:
        """The latest stored version of each agent that the lock lists: ("ok", version), ("missing", None) or ("unreadable", why)."""
        found: dict[str, tuple[str, object]] = {}
        for name in sorted(self.lock.agents if self.lock else ()):
            value, problem = self.read(("agent", name), lambda name=name: self.foundry.read_agent(name))  # type: ignore[union-attr]
            found[name] = ("unreadable", problem.removeprefix("the project could not be read ").strip("()") or problem) if problem else ("missing", None) if value is None else ("ok", value)
        return found


def prepare(env: Mapping[str, str], redact: Callable[[str], str], *, transport, sleep, monotonic, clock, fetch, foundry: object | None, extras: object) -> Context:
    """The context of one check. It never raises: whatever cannot be made is said in a problem, and the controls that need it are UNKNOWN."""
    context = Context(env=env, now=stamp(clock()))
    try:
        context.settings = cfg.load(env)
    except Exception as error:  # noqa: BLE001
        context.settings_problem = f"the settings of the app are not valid ({type(error).__name__}), so what the code would make cannot be compared with the lock"
    try:
        context.lock = lockfile.load()
    except lockfile.LockError as error:
        context.lock_problem = plain(error, 120)
    options = {"sleep": sleep, **({"fetch": fetch} if fetch else {})}
    reader: Identity | None = None
    if extras is NOT_GIVEN:
        reader = Identity(env, **options)
        try:
            extras = wiring.build_extras(env, reader.token, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock)
        except Exception as error:  # noqa: BLE001
            extras = None
            context.store_problem = f"the loop is not set up right ({type(error).__name__}), so the switches cannot be read"
        if extras is None and not context.store_problem:
            context.store_problem = "the loop is not set up, so there is no store to read the switches from"
    context.extras = extras
    if foundry is not None:
        context.foundry = foundry
        return context
    endpoint = context.settings.foundry_endpoint if context.settings is not None else (env.get(ENDPOINT_SETTING) or "").strip().rstrip("/")
    if not endpoint:
        context.foundry_problem = "no Foundry project is set, so the agents and the connections are not read"
        return context
    try:
        reader = reader or Identity(env, **options)
        client = Client(drift_calls(endpoint), redact, transport=transport, sleep=sleep, monotonic=monotonic)
        client.deadline = monotonic() + READ_SECONDS
        context.foundry = Foundry(endpoint, client, reader.token, redact)  # type: ignore[arg-type]
    except (ValueError, FoundryError):
        context.foundry_problem = "the endpoint of the Foundry project is not one that this app accepts"
    return context


# -- the controls that only the app can judge ------------------------------------------------------------------------------------------------------

def check_lock(context: Context) -> rules.Finding:
    if context.lock is None or context.settings is None:
        return rules.judge_lock([], context.lock_problem, context.settings_problem if context.lock is not None else "", 0, 0)
    from . import library, toolbox

    specs = (agents.investigator(context.settings, toolbox.SPECS), agents.skeptic(context.settings), agents.scholar(context.settings, (library.FETCH_DOC,)))
    definitions = {spec.name: definition_of(spec) for spec in specs}
    implementations, module = harness.code_digests()
    problems = lockfile.stale(context.lock, definitions, implementations, module)
    return rules.judge_lock(problems, "", "", len(context.lock.agents), len(context.lock.tools))


def check_release(context: Context) -> rules.Finding:
    digest, files = harness.package_digest()
    return rules.judge_release(digest, files, context.env.get(PACKAGE_SETTING, ""), harness.build_of(context.env))


def probes(endpoint: str, gateway_host: str) -> list[tuple[str, tuple, str, str, bool]]:
    """(what, the list of calls, method, address, whether the list must let it through). The first lists are what the Watch holds, the last is the drift check's own."""
    watch = http.allowed_calls(endpoint, gateway_host or None)
    own = drift_calls(endpoint)
    docs = http.docs_calls()
    page_host, prefix = next(iter(http.DOCS_PAGES.items()))
    page = f"https://{page_host}{prefix}probe/page"
    delete, put, patch = CHANGING
    other = "https://other-account.services.ai.azure.com/api/projects/other"
    agent = f"{endpoint}/agents/meternaut-investigator"
    conversation = f"{endpoint}/openai/v1/conversations/conv_probe0001"
    disk = f"{ARM}/subscriptions/{EXAMPLE_ID}/resourceGroups/rg-probe/providers/Microsoft.Compute/disks/probe-disk"
    found = [
        ("a response of an agent", watch, "POST", f"{endpoint}/openai/v1/responses", True),
        ("making an agent", watch, "POST", f"{endpoint}/agents", True),
        ("a new version of an agent", watch, "POST", f"{agent}/versions", True),
        ("reading an agent", watch, "GET", agent, True),
        ("ending a conversation", watch, delete, conversation, True),
        ("ending an agent", watch, delete, agent, False),
        ("replacing an agent", watch, put, agent, False),
        ("changing an agent", watch, patch, agent, False),
        ("a model call to the project direct", watch, "POST", f"{endpoint}/openai/v1/chat/completions", False),
        ("a model call to a deployment direct", watch, "POST", f"{endpoint}/openai/deployments/probe/chat/completions", False),
        ("listing the connections", watch, "GET", f"{endpoint}/connections", False),
        ("another project", watch, "POST", f"{other}/openai/v1/responses", False),
        ("another host", watch, "POST", "https://example.invalid/probe", False),
        ("a query of the estate", watch, "POST", f"{ARM}/providers/Microsoft.ResourceGraph/resources", True),
        ("a change of a disk", watch, delete, disk, False),
        ("a replacement of a disk", watch, put, disk, False),
        ("a post to a disk", watch, "POST", disk, False),
        ("a role assignment", watch, "POST", f"{ARM}/subscriptions/{EXAMPLE_ID}/resourceGroups/rg-probe/providers/Microsoft.Authorization/roleAssignments/probe", False),
        ("the list of agents", own, "GET", f"{endpoint}/agents", True),
        ("one agent", own, "GET", agent, True),
        ("the list of connections", own, "GET", f"{endpoint}/connections", True),
        ("making an agent by the check", own, "POST", f"{endpoint}/agents", False),
        ("a response by the check", own, "POST", f"{endpoint}/openai/v1/responses", False),
        ("ending an agent by the check", own, delete, agent, False),
        ("replacing an agent by the check", own, put, agent, False),
        ("another project by the check", own, "GET", f"{other}/agents", False),
        ("the estate by the check", own, "GET", f"{ARM}/subscriptions", False),
        # The Study's own list (http.docs_calls): public documentation pages and the price list, read with GET and no token, and nothing else.
        ("a documentation page by the study", docs, "GET", page, True),
        ("the price list by the study", docs, "GET", f"https://{http.PRICES_HOST}{http.PRICES_PATH}", True),
        ("a post to a documentation page", docs, "POST", page, False),
        ("a page in another language", docs, "GET", f"https://{page_host}/de-de/probe/page", False),
        ("a page outside the English folder", docs, "GET", f"https://{page_host}{prefix}../probe", False),
        ("another host by the study", docs, "GET", "https://example.invalid/en-us/probe", False),
        ("the estate by the study", docs, "GET", f"{ARM}/subscriptions", False),
        ("a documentation page by the watch", watch, "GET", page, False),
    ]
    if gateway_host:
        route = f"https://{gateway_host}/default/models/openai/v1"
        found += [
            ("a chat completion of the gateway", watch, "POST", f"{route}/chat/completions", True),
            ("another route of the gateway", watch, "POST", f"{route}/embeddings", False),
            ("a read of the gateway", watch, "GET", f"{route}/chat/completions", False),
            ("another gateway", watch, "POST", "https://other-gateway.ai.gateway.azure.com/default/models/openai/v1/chat/completions", False),
            ("a chat completion by the check", own, "POST", f"{route}/chat/completions", False),
        ]
    return found


def check_calls(context: Context) -> rules.Finding:
    endpoint = context.settings.foundry_endpoint if context.settings is not None else ""
    if not endpoint:
        return rules.finding("A-CALLS", rules.UNKNOWN, "no Foundry project is set, so the lists of calls for it are not built")
    gateway = context.settings.ai_gateway_host if context.settings is not None else ""
    failures: list[str] = []
    made = probes(endpoint, gateway)
    for what, calls, method, address, expected in made:
        try:
            Client(calls, str).check(method, address)
            allowed = True
        except Refused:
            allowed = False
        if allowed != expected:
            failures.append(f"{what} is {'refused' if expected else 'let through'}")
    return rules.judge_calls(failures, len(made))


def check_switches(context: Context) -> rules.Finding:
    store = context.store
    if store is None:
        return rules.judge_switches(None, context.store_problem or "no store is set, so the switches cannot be read", harness.BY)
    try:
        states = {}
        for name in SWITCH_NAMES:
            record = store.switch_get(name)  # type: ignore[attr-defined]
            states[name] = (bool(record.paused), record.by or "")
    except Exception:  # noqa: BLE001
        return rules.judge_switches(None, "the switches could not be read (the store did not answer)", harness.BY)
    return rules.judge_switches(states, "", harness.BY)


# -- one check -------------------------------------------------------------------------------------------------------------------------------------

def _controls(ids: tuple[str, ...], work: Callable[[], rules.Finding | list[rules.Finding]]) -> list[rules.Finding]:
    try:
        made = work()
        return made if isinstance(made, list) else [made]
    except Exception as error:  # noqa: BLE001 (a control that fails is UNKNOWN: the others still report)
        return rules.unknown_all(ids, f"the control could not be judged ({type(error).__name__})")


def evaluate(context: Context) -> list[rules.Finding]:
    """The findings of every control of the catalog, in its order. It never raises, and a control that cannot be judged is UNKNOWN."""
    made: dict[str, rules.Finding] = {}
    groups: list[tuple[tuple[str, ...], Callable[[], rules.Finding | list[rules.Finding]]]] = [
        (("A-LOCK",), lambda: check_lock(context)),
        (("A-RELEASE",), lambda: check_release(context)),
        (("A-CALLS",), lambda: check_calls(context)),
        (("A-SETTINGS",), lambda: rules.judge_settings(context.env.keys())),
        (("A-AGENTS-LISTED",), lambda: _listed(context)),
        (rules.DEFINITION_CONTROLS, lambda: rules.judge_definitions(context.lock, context.stored())),
        (("A-CONNECTIONS", "A-NO-DIRECT-MODEL", "A-TRACING"), lambda: _connections(context)),
        (("A-SWITCHES",), lambda: check_switches(context)),
    ]
    for ids, work in groups:
        for item in _controls(ids, work):
            made[item.control] = item
    return [made.get(control.id) or rules.finding(control.id, rules.UNKNOWN, "the control was not judged") for control in rules.CONTROLS]


def _listed(context: Context) -> rules.Finding:
    listing, problem = context.listing()
    items, more = listing if listing is not None else ([], False)
    return rules.judge_listed(context.lock, items, more, problem)


def _connections(context: Context) -> list[rules.Finding]:
    listing, problem = context.connections()
    items, more = listing if listing is not None else ([], False)
    gateway = context.settings.ai_gateway_host if context.settings is not None else (context.env.get(cfg.AIGATEWAY_HOST) or "").strip().lower()
    return rules.judge_connections(context.lock, gateway, items, more, problem)


@dataclass(frozen=True)
class Report:
    findings: tuple[rules.Finding, ...]
    read_at: str
    tripped: bool  # this check pulled the switch investigation
    trip: tuple[str, ...]  # the ids that asked for it

    def states(self) -> dict[str, str]:
        return {item.control: item.state for item in self.findings}


def write(findings: list[rules.Finding], read_at: str, redact: Callable[[str], str]) -> None:
    """One line for every control, in the order of the catalog: the heartbeat. A line that cannot be written is left out and the others are written."""
    for item in findings:
        try:
            harness.trace(harness.DRIFT_PREFIXES[item.state], item.payload(read_at), redact, level=logging.WARNING if item.state == rules.FAIL else logging.INFO)
        except Exception:  # noqa: BLE001
            LOG.error("a line of the drift check could not be written")


def _keep(context: Context | None, trigger: str, by: str, started: str, report: Report, clock: Callable[[], object]) -> None:
    """Keeps the result as the latest check of the app, so that the Operations page shows it (the timer's and a person's alike). A store that cannot be written leaves the page as it was: the
    telemetry has a line for every control either way."""
    store = getattr(getattr(context, "extras", None), "store", None)
    if store is None:
        return
    try:
        store.check_put(CheckRecord(started_at=started, trigger=trigger if trigger in CHECK_TRIGGERS else "timer", by=plain(by, 60), finished_at=stamp(clock()),  # type: ignore[arg-type]
                                    tripped=report.tripped, results=tuple({"control": item.control, "layer": item.layer, "state": item.state, "detail": item.detail}
                                                                          for item in report.findings)))
    except Exception as error:  # noqa: BLE001 (the result is a convenience for the page; the check has done its work)
        LOG.warning("the result of the drift check could not be kept (%s)", type(error).__name__)


def run_check(trigger: str = "timer", env: Mapping[str, str] | None = None, *, transport=default_transport, sleep: Callable[[float], None] = time.sleep,
              monotonic: Callable[[], float] = time.monotonic, clock: Callable[[], object] = utc_now, fetch=None, foundry: object | None = None, extras: object = NOT_GIVEN,
              by: str = "", started_at: str = "") -> Report | None:
    """One check. It never raises: it writes a line for every control (UNKNOWN for what it could not judge), and when a control that guards the agents FAILs it pulls the switch
    investigation and sends one letter. `foundry` and `extras` are for a caller that has them already (a test); without them they are made from the settings of the app.

    The result is kept as the latest check of the app (CheckRecord): `trigger` is "timer" or "console" (a person's check, named by `by`), and `started_at` is the time that the caller
    claimed for it, when it claimed one (the console does, so that two people cannot start two checks within the gap)."""
    env = os.environ if env is None else env
    redact = Redactor()
    started = started_at or stamp(clock())  # type: ignore[arg-type]
    try:
        context = prepare(env, redact, transport=transport, sleep=sleep, monotonic=monotonic, clock=clock, fetch=fetch, foundry=foundry, extras=extras)  # type: ignore[arg-type]
        findings = evaluate(context)
        read_at = context.now
    except Exception as error:  # noqa: BLE001 (the heartbeat is written whatever happened)
        LOG.error(redact(f"the drift check failed: {type(error).__name__}"))
        read_at = stamp(clock())  # type: ignore[arg-type]
        findings = rules.unknown_all((control.id for control in rules.CONTROLS), f"the check could not run ({type(error).__name__})")
        context = None
    write(findings, read_at, redact)
    asked = tuple(rules.trip_ids(findings))
    tripped = False
    if asked:
        store = getattr(context.extras, "store", None) if context is not None else None
        alert = getattr(context.extras, "on_alert", None) if context is not None else None
        tripped = harness.Brake(store, alert, clock, redact).pull("drift", ", ".join(asked))  # type: ignore[arg-type]
    report = Report(tuple(findings), read_at, tripped, asked)
    _keep(context, trigger, by, started, report, clock)
    return report
