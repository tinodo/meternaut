"""The rules of the drift check: what each control looks at and when it passes, fails or cannot tell. Pure functions of plain data.

The drift check reads, once a day, what the agents are and holds it against what the repository says (cases/drift.py in the app, tools/agents-drift.py from inside the network). The reading
is theirs; the judging is here, so that both of them, and the tests, judge alike. This module is standard library only and imports only lockfile.py and plaintext.py (a tool of the
Operator loads the three from one folder), and it never reads, writes or calls anything.

A control has an id (`A-` for the controls of the agents; the independent check of the control plane has ids of its own in the same report shape), a layer of the AI Citadel blueprint
(L1 the gateway and what leads to it, L2 the operation of the agents, L3 their management and owners) and a state:

  PASS     what was read is what the repository says.
  FAIL     what was read is a fact that is not what the repository says.
  UNKNOWN  nothing can be said: the read failed, the thing is not there yet, or what was read has a shape that the control does not know. UNKNOWN is never a PASS and never a trip.

A FAIL of a control whose `guard` is true pulls the switch `investigation` (the narrowest brake: only the agents stop, and a person releases it). The others are told on the telemetry
only. Every detail is plain text made of the words of this code, counts, ids of controls and names that this repository gives (agents, tools, one connection); the text of a project, an
estate or a model never gets into one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from . import lockfile
from .plaintext import plain

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
STATES = (PASS, FAIL, UNKNOWN)
MAX_NAMES = 4
MAX_SAID = 3


@dataclass(frozen=True)
class Control:
    id: str
    layer: str
    guard: bool  # a FAIL pulls the switch investigation
    says: str  # what it holds, in one plain sentence


# The in-app drift check, the data-plane half. The ids are the ones that the telemetry, the alert rules and the proposal name; a test holds this list against the proposal.
CONTROLS = (
    Control("A-LOCK", "L2", True, "The agents that the code would make, the schemas and the code of their tools equal the lock agents.lock.json."),
    Control("A-RELEASE", "L2", True, "The digest of the files that run equals PACKAGE_SHA256, the digest of the release; unknown when the app setting is not there."),
    Control("A-CALLS", "L2", True, "The lists of calls that the process holds refuse a change of an agent, a model call that is not through the AI Gateway and a change of Azure."),
    Control("A-SETTINGS", "L2", False, "No setting of the app is named like a key, a secret, a connection string or a model that bypasses the gateway (names only, never values)."),
    Control("A-AGENTS-LISTED", "L2", False, "The Foundry project holds no agent that the lock does not list."),
    Control("A-DEF-MODEL", "L2", True, "The latest stored version of each agent has the locked kind, model alias and gateway connection."),
    Control("A-DEF-INSTRUCTIONS", "L2", True, "The latest stored version of each agent has the locked instructions."),
    Control("A-DEF-TOOLS", "L2", True, "The latest stored version of each agent has the locked function tools, and no tool of another kind."),
    Control("A-DEF-OPTIONS", "L2", True, "The latest stored version of each agent has the locked reasoning effort and guardrail policy; an option that nobody listed is unknown, not a failure."),
    Control("A-CONNECTIONS", "L1", True, "The connection that leads to the AI Gateway is there, points at the gateway of the app and authenticates with no key."),
    Control("A-NO-DIRECT-MODEL", "L1", False, "The project holds no other connection of a model kind: no model is reached except through the gateway."),
    Control("A-TRACING", "L2", False, "The project has the connection that sends the traces of the agents to Application Insights."),
    Control("A-SWITCHES", "L2", False, "The four switches can be read, and no trip of the agent harness or of this check waits for a person."),
)
BY_ID = {control.id: control for control in CONTROLS}
DEFINITION_CONTROLS = ("A-DEF-MODEL", "A-DEF-INSTRUCTIONS", "A-DEF-TOOLS", "A-DEF-OPTIONS")

# The words of the kinds that the data plane shows for a connection and for the way it signs in, lower case and without _ and -. A kind that is in none of the lists is not decided.
KEYED = frozenset({"apikey", "customkeys", "account" "key", "sas", "sastoken", "username" "pass" "word", "pat", "oauth2", "serviceprincipal", "key"})
KEYLESS = frozenset({"aad", "entra", "none", "managedidentity", "projectmanagedidentity", "systemassignedidentity", "userassignedidentity", "agenticidentity", "agenticidentitytoken"})
MODEL_KINDS = frozenset({"azureopenai", "openai", "aiservices", "azureaiservices", "cognitiveservice", "cognitiveservices", "serverless", "modelgateway", "apimanagement", "azureaifoundry"})
TRACE_KINDS = frozenset({"appinsights", "applicationinsights"})


@dataclass(frozen=True)
class Finding:
    control: str
    state: str
    detail: str

    @property
    def layer(self) -> str:
        return BY_ID[self.control].layer

    @property
    def guard(self) -> bool:
        return BY_ID[self.control].guard

    def payload(self, read_at: str) -> dict:
        """The one report shape of every drift check: {"control", "layer", "state", "detail", "readAt"}."""
        return {"control": self.control, "layer": self.layer, "state": self.state, "detail": self.detail, "readAt": read_at}


def finding(control: str, state: str, detail: str) -> Finding:
    if control not in BY_ID or state not in STATES:
        raise ValueError("a finding is of a control of the catalog and of a state of PASS, FAIL or UNKNOWN")
    return Finding(control, state, plain(detail))


def unknown_all(controls: Iterable[str], detail: str) -> list[Finding]:
    return [finding(control, UNKNOWN, detail) for control in controls]


def _kind(value: object) -> str:
    return re.sub(r"[_\s-]", "", value).lower() if isinstance(value, str) else ""


def _names(names: Iterable[object], limit: int = MAX_NAMES) -> str:
    items = list(names)
    shown = [plain(name, 64) for name in items[:limit]]
    return ", ".join(shown) + (f" and {len(items) - limit} more" if len(items) > limit else "")


def _said(things: list[str]) -> str:
    return "; ".join(things[:MAX_SAID]) + (f"; and {len(things) - MAX_SAID} more" if len(things) > MAX_SAID else "")


# -- the agents in the project ---------------------------------------------------------------------------------------------------------------------

def judge_listed(lock: lockfile.Lock | None, items: list[Mapping], more: bool, problem: str) -> Finding:
    """A-AGENTS-LISTED. `items` are the agents of the project as {"name"} (None for a name that this app does not accept); `more` says that the list goes on after the pages that were read."""
    if problem:
        return finding("A-AGENTS-LISTED", UNKNOWN, problem)
    if lock is None:
        return finding("A-AGENTS-LISTED", UNKNOWN, "there is no lock to hold the agents of the project against")
    unlisted = [item.get("name") for item in items if item.get("name") not in lock.agents]
    if unlisted:
        named = [name for name in unlisted if name]
        odd = len(unlisted) - len(named)
        text = f"{len(unlisted)} agent{'' if len(unlisted) == 1 else 's'} of the project {'is' if len(unlisted) == 1 else 'are'} not in the lock"
        if named:
            text += f": {_names(named)}"
        if odd:
            text += f" ({odd} with a name that this app does not accept)"
        return finding("A-AGENTS-LISTED", FAIL, text)
    if more:
        return finding("A-AGENTS-LISTED", UNKNOWN, "the list of agents goes on after the pages that were read")
    return finding("A-AGENTS-LISTED", PASS, f"{len(items)} agent{'' if len(items) == 1 else 's'} in the project, all of them in the lock")


def judge_definitions(lock: lockfile.Lock | None, stored: Mapping[str, tuple[str, object]]) -> list[Finding]:
    """The four A-DEF controls. `stored` maps the name of each locked agent to ("ok", the latest version as the project stores it), ("missing", None) or ("unreadable", why)."""
    if lock is None:
        return unknown_all(DEFINITION_CONTROLS, "there is no lock to hold the stored agents against")
    differences: dict[str, list[str]] = {control: [] for control in DEFINITION_CONTROLS}
    options: list[str] = []
    unread: list[str] = []
    missing: list[str] = []
    for name in sorted(lock.agents):
        status, value = stored.get(name, ("unreadable", "the agent was not read"))
        if status == "missing":
            missing.append(name)
            continue
        definition = value.get("definition") if status == "ok" and isinstance(value, Mapping) else None
        if not isinstance(definition, Mapping):
            unread.append(f"{name} ({plain(value, 60)})" if status == "unreadable" and isinstance(value, str) else f"{name} (the stored version shows no definition)")
            continue
        for difference in lockfile.compare(lock.agents[name], lockfile.facts_of(definition, lock.ignored)):
            if difference.certain:
                differences[difference.control].append(f"{name}: {difference.what}")
            else:
                options.append(f"{name}: {difference.what}")
    found: list[Finding] = []
    for control in DEFINITION_CONTROLS:
        if differences[control]:
            found.append(finding(control, FAIL, _said(differences[control])))
        elif unread or missing or (control == "A-DEF-OPTIONS" and options):
            reasons = []
            if unread:
                reasons.append(f"cannot be read: {_names(unread)}")
            if missing:
                reasons.append(f"not in the project yet: {_names(missing)}")
            if control == "A-DEF-OPTIONS" and options:
                reasons.append(_said(options))
            found.append(finding(control, UNKNOWN, "; ".join(reasons)))
        else:
            found.append(finding(control, PASS, f"the latest versions of {len(lock.agents)} agents equal the lock"))
    return found


# -- the connections of the project ----------------------------------------------------------------------------------------------------------------

def _host(target: object) -> str:
    try:
        return (urlsplit(target).hostname or "").lower() if isinstance(target, str) else ""
    except ValueError:
        return ""


def judge_connections(lock: lockfile.Lock | None, gateway_host: str, items: list[Mapping], more: bool, problem: str) -> list[Finding]:
    """A-CONNECTIONS, A-NO-DIRECT-MODEL and A-TRACING from the connections of the project as {"name", "type", "target", "credentials"} (None for what this app does not accept)."""
    controls = ("A-CONNECTIONS", "A-NO-DIRECT-MODEL", "A-TRACING")
    if problem:
        return unknown_all(controls, problem)
    name = lock.connection if lock is not None else ""
    if lock is None:
        gateway = finding("A-CONNECTIONS", UNKNOWN, "there is no lock to hold the connections against")
    elif not name:
        gateway = finding("A-CONNECTIONS", FAIL, "the lock names no connection to the AI Gateway, so the models of the agents are not locked to it")
    else:
        named = [item for item in items if item.get("name") == name]
        if not named:
            gateway = finding("A-CONNECTIONS", UNKNOWN if more else FAIL, f"the project has no connection named {name}" if not more else "the list of connections goes on after the pages that were read")
        elif len(named) > 1:
            gateway = finding("A-CONNECTIONS", UNKNOWN, f"the project shows {len(named)} connections named {name}")
        else:
            connection = named[0]
            wrong: list[str] = []
            unsure: list[str] = []
            host = _host(connection.get("target"))
            if not gateway_host:
                unsure.append("the app has no host of the AI Gateway to compare with")
            elif not host:
                unsure.append("the connection shows no target")
            elif host != gateway_host.lower():
                wrong.append("the connection points at a host that is not the AI Gateway of the app")
            kind = _kind(connection.get("credentials"))
            if kind in KEYED:
                wrong.append("the connection authenticates with a key")
            elif kind not in KEYLESS:
                unsure.append("the connection shows no kind of sign-in that is known to be keyless")
            gateway = (finding("A-CONNECTIONS", FAIL, "; ".join(wrong)) if wrong else finding("A-CONNECTIONS", UNKNOWN, "; ".join(unsure)) if unsure
                       else finding("A-CONNECTIONS", PASS, f"the connection {name} points at the AI Gateway of the app and authenticates with no key"))
    others = [item for item in items if item.get("name") is None or item.get("name") != name]
    direct = [item for item in others if _kind(item.get("type")) in MODEL_KINDS]
    unclassified = [item for item in others if not _kind(item.get("type"))]
    if lock is None:
        no_direct = finding("A-NO-DIRECT-MODEL", UNKNOWN, "there is no lock to say which connection is the one to the AI Gateway")
    elif direct:
        no_direct = finding("A-NO-DIRECT-MODEL", FAIL, f"{len(direct)} other connection{'' if len(direct) == 1 else 's'} of a model kind: " + _names(item.get("name") or "a name that this app does not accept" for item in direct))
    elif unclassified or more:
        no_direct = finding("A-NO-DIRECT-MODEL", UNKNOWN, f"{len(unclassified)} connection{'' if len(unclassified) == 1 else 's'} of a kind that is not shown" if unclassified else "the list of connections goes on after the pages that were read")
    else:
        no_direct = finding("A-NO-DIRECT-MODEL", PASS, f"{len(others)} other connection{'' if len(others) == 1 else 's'}, none of a model kind")
    traced = [item for item in items if _kind(item.get("type")) in TRACE_KINDS]
    if traced:
        tracing = finding("A-TRACING", PASS, "the project has the connection that sends the traces of the agents to Application Insights")
    elif more or unclassified:
        tracing = finding("A-TRACING", UNKNOWN, "the connections that were read do not show one for Application Insights, and not every connection was read or classified")
    else:
        tracing = finding("A-TRACING", FAIL, "the project has no connection to Application Insights, so the traces of the agents do not reach it")
    return [gateway, no_direct, tracing]


# -- what the app knows about itself ---------------------------------------------------------------------------------------------------------------

# Names that a key, a secret or a connection string leaves behind. They are spelled in pieces: the packaging test looks for the whole words in the files of the app.
_KEY_NAMES = re.compile(
    r"(?:^|[_.-])(?:api|access|account|primary|secondary|private|master|shared[_-]?access)[_-]?key(?:[_-]?[12])?$"
    r"|(?:^|[_.-])(?:client[_-]?)?secret$"
    r"|(?:^|[_.-])pass" r"(?:word|wd)$"
    r"|(?:^|[_.-])sas(?:[_-]?(?:token|url))?$"
    r"|(?:^|[_.-])(?:auth|bearer|refresh)[_-]?token$"
    r"|(?:^|[_.-])conn(?:ection)?[_-]?str(?:ing)?$"
    r"|^AzureWebJobs(?:Storage|Dashboard)$",
    re.I)
# What a direct route to a model would be called: the app reads none of these, so one that is there is somebody's doing.
_DIRECT_NAMES = re.compile(r"openai|deployment[_-]?name|inference[_-]?(?:endpoint|url)|azure[_-]?ai[_-]?(?:endpoint|key|project)", re.I)
# Set by the platform or by the template, and known not to hold a secret that anything accepts: the connection string of Application Insights names the component (the component takes only
# tokens of the app's identity), and the platform sets the secret of its own identity endpoint.
_EXEMPT = frozenset({("APPLICATIONINSIGHTS_" + "CONNECTION" + "_" + "STRING").lower(), "applicationinsights_authentication_string", "msi_secret"})
# The platform keeps a copy of every setting of the app in the environment of the process under the name `APPSETTING_<name>`, so the same name is read twice. The copy is the setting itself and is
# judged as it (the first real run of the check, 2026-11-09, failed on the copy of the connection string of Application Insights, which the setting itself is exempt for).
_PLATFORM_COPY = re.compile(r"^APPSETTING_", re.I)


def judge_settings(names: Iterable[str]) -> Finding:
    """A-SETTINGS from the names of the settings of the app (never their values)."""
    seen = sorted({_PLATFORM_COPY.sub("", name) or name for name in names if isinstance(name, str) and name})
    keyed = [name for name in seen if name.lower() not in _EXEMPT and _KEY_NAMES.search(name)]
    direct = [name for name in seen if name.lower() not in _EXEMPT and name not in keyed and _DIRECT_NAMES.search(name)]
    if keyed or direct:
        parts = []
        if keyed:
            parts.append(f"{len(keyed)} named like a key, a secret or a connection string: {_names(keyed)}")
        if direct:
            parts.append(f"{len(direct)} named like a model that bypasses the gateway: {_names(direct)}")
        return finding("A-SETTINGS", FAIL, "settings " + "; ".join(parts))
    return finding("A-SETTINGS", PASS, f"{len(seen)} settings read, none named like a key, a secret, a connection string or a direct route to a model")


def judge_release(digest: str, files: int, released: str, build: str) -> Finding:
    """A-RELEASE. `digest` is the digest that the running files make, `released` the value of PACKAGE_SHA256 (empty when it is not set)."""
    if not digest:
        return finding("A-RELEASE", UNKNOWN, "the files of the app cannot be read, so their digest is not known")
    released = (released or "").strip().lower()
    if not released:
        return finding("A-RELEASE", UNKNOWN, f"PACKAGE_SHA256 is not set, so the running files cannot be held against the release (live {digest[:12]}, {files} files, build {build})")
    if not re.fullmatch(r"[0-9a-f]{64}", released):
        return finding("A-RELEASE", UNKNOWN, "PACKAGE_SHA256 is not a SHA-256 in hexadecimal, so the running files cannot be held against the release")
    if released != digest:
        return finding("A-RELEASE", FAIL, f"the files that run are not the files that were released (live {digest[:12]}, released {released[:12]}, {files} files, build {build})")
    return finding("A-RELEASE", PASS, f"the {files} files that run are the files that were released ({digest[:12]}, build {build})")


def judge_switches(states: Mapping[str, tuple[bool, str]] | None, problem: str, automatic: str) -> Finding:
    """A-SWITCHES. `states` maps each switch to (pulled, who pulled it); `automatic` is the name that the harness and this check pull a switch by."""
    if states is None:
        return finding("A-SWITCHES", UNKNOWN, problem or "the switches could not be read")
    pulled = sorted(name for name, (paused, _) in states.items() if paused)
    waiting = sorted(name for name, (paused, by) in states.items() if paused and by == automatic)
    if waiting:
        return finding("A-SWITCHES", FAIL, f"a trip waits for a person: the switch {_names(waiting)} was pulled by the safeguards and nobody has released it")
    return finding("A-SWITCHES", PASS, f"{len(states)} switches read; " + (f"pulled by a person: {_names(pulled)}" if pulled else "none is pulled"))


def judge_calls(failures: list[str], probes: int) -> Finding:
    """A-CALLS from the probes of the lists of calls that did not come out as they must."""
    if failures:
        return finding("A-CALLS", FAIL, f"{len(failures)} of {probes} probes of the lists of calls came out wrong: " + _said(failures))
    return finding("A-CALLS", PASS, f"{probes} probes of the lists of calls came out as they must")


def judge_lock(problems: list[str], lock_problem: str, settings_problem: str, agents: int, tools: int) -> Finding:
    """A-LOCK from what differs between the code and the lock (lockfile.stale)."""
    if lock_problem:
        return finding("A-LOCK", FAIL, f"the lock of the agents cannot be used ({lock_problem})")
    if settings_problem:
        return finding("A-LOCK", UNKNOWN, settings_problem)
    if problems:
        return finding("A-LOCK", FAIL, f"{len(problems)} difference{'' if len(problems) == 1 else 's'} between the code and the lock: " + _said(problems))
    return finding("A-LOCK", PASS, f"the code of {agents} agents and {tools} tools equals the lock")


def trip_ids(findings: Iterable[Finding]) -> list[str]:
    """The ids of the controls whose FAIL pulls the switch."""
    return [item.control for item in findings if item.state == FAIL and item.guard]
