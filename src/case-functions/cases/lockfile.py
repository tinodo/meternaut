"""The lock of the agents: what each agent of the investigation is allowed to be, as hash values, and the one way to compare a definition with it.

`agents.lock.json` (next to this file, so that it travels in the package) holds, for each agent, the model alias, the SHA-256 of its instructions, the SHA-256 of the
canonical schemas of its tools and the options that are expected, and, for each tool, the SHA-256 of its schema and of the source of the code that runs it. It holds no id,
no name and no address of an estate: a definition is made of what this repository says, and the lock is made from it by `tools/agents-lock.py write`. A changed definition is a
release: one pull request changes the code and the lock together, and a test fails when they differ. Nobody changes an agent in the portal.

The same function reads the definition that the code sends (foundry.definition_of) and the definition that the service stores (the `definition` of a version), so that both are
reduced to the same facts and compared by the same rules. The service adds defaults to what it stores (it stored `temperature` and `top_p`: tests/test_foundry.py), so only what the lock
pins is compared: the kind, the model (the connection and the alias), the instructions, the function tools (their names and the canonical form of their schemas), the reasoning effort and
the guardrail policy. A key of the definition that the lock neither pins nor ignores is an option that nobody listed.

This module is standard library only and imports nothing of the package, so that a tool of the Operator can load it from its own folder (tools/agents-drift.py does).
"""
from __future__ import annotations

import hashlib
import inspect
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

SCHEMA = 1
FILE_NAME = "agents.lock.json"
FUNCTION = "function"
SHA = re.compile(r"[0-9a-f]{64}")
NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9])?")
WORD = re.compile(r"[A-Za-z0-9._-]{1,64}")
KIND = re.compile(r"[a-z_]{1,40}")
# The keys of a prompt definition that this module reads, and the ones that the lock ignores (the service adds them as defaults). Any other key is an option nobody listed.
READ_KEYS = ("kind", "model", "instructions", "tools", "reasoning", "rai_config")
DEFAULT_IGNORED = ("temperature", "top_p")
# What a difference is called, and the control of the drift check that it belongs to (cases/drift.py).
CODES = {
    "kind": "A-DEF-MODEL", "model": "A-DEF-MODEL", "connection": "A-DEF-MODEL",
    "instructions": "A-DEF-INSTRUCTIONS",
    "tools": "A-DEF-TOOLS", "tool-kind": "A-DEF-TOOLS",
    "effort": "A-DEF-OPTIONS", "rai": "A-DEF-OPTIONS", "option": "A-DEF-OPTIONS",
}
# The differences that are certain facts about a definition (a model, the instructions, a tool, the guardrail). An option that nobody listed is not certain to be harmful: it is
# reported as not decided, never as a failure.
CERTAIN = tuple(code for code in CODES if code != "option")


class LockError(Exception):
    """The lock cannot be read or is not what it must be. The text says what, and holds no value of the lock."""


def canonical(value: object) -> str:
    """One JSON text for one value: sorted keys, no white space, ASCII only. The hash of it is the same on every machine."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest(value: object) -> str:
    return sha256_text(canonical(value))


def normalize_source(text: str) -> str:
    """Source code as it is hashed: line ends are LF, no white space at the end of a line, no empty lines at the end. A checkout on Windows and one on Linux then hash alike."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).rstrip("\n") + "\n"


def source_digest(text: str) -> str:
    return sha256_text(normalize_source(text))


def implementation_digests(toolbox: type, names: Iterable[str]) -> dict[str, str]:
    """For each tool name, the digest of the source of the method that runs it: `Toolbox._tool_<name>`. A tool whose method cannot be found or read has an empty digest,
    which never equals a locked one."""
    found: dict[str, str] = {}
    for name in names:
        method = getattr(toolbox, f"_tool_{name}", None)
        try:
            found[name] = source_digest(inspect.getsource(method)) if method is not None else ""
        except (OSError, TypeError):
            found[name] = ""
    return found


# -- what a definition says -----------------------------------------------------------------------------------------------------------------------

def schema_of(tool: Mapping) -> dict:
    """The part of a function tool that is pinned: its name, its description and the schema of its arguments. `strict` is not pinned: the app checks every call itself."""
    return {"name": tool.get("name"), "description": tool.get("description", ""), "parameters": tool.get("parameters", {})}


def tools_digest(tools: Iterable[Mapping]) -> str:
    return digest(sorted((schema_of(tool) for tool in tools), key=lambda schema: str(schema["name"])))


@dataclass(frozen=True)
class Facts:
    """What a definition says, reduced to what the lock pins."""

    kind: str
    model: str  # the alias: the part of the model name after the connection
    connection: str  # "" when the model is a deployment of the project itself
    instructions_sha256: str
    tool_names: tuple[str, ...]  # the function tools, sorted
    tools_sha256: str
    foreign_tools: tuple[str, ...]  # the kinds of the tools that are not function tools, sorted
    effort: str | None
    rai_policy: str | None
    options: tuple[str, ...]  # keys that the lock neither pins nor ignores, sorted


def _plain(value: object, pattern: re.Pattern, other: str = "other") -> str:
    return value if isinstance(value, str) and pattern.fullmatch(value) else other


def facts_of(definition: Mapping, ignored: Iterable[str] = DEFAULT_IGNORED) -> Facts:
    """The facts of a definition: the one that this code sends or the one that the service stores. What is not there is empty, never an error."""
    ignored = set(ignored)
    model = definition.get("model") if isinstance(definition.get("model"), str) else ""
    connection, slash, rest = model.partition("/")
    connection, alias = (connection, rest) if slash and rest else ("", model)
    tools = definition.get("tools") if isinstance(definition.get("tools"), list) else []
    functions = [tool for tool in tools if isinstance(tool, dict) and tool.get("type") == FUNCTION]
    foreign = sorted(_plain(tool.get("type") if isinstance(tool, dict) else None, KIND) for tool in tools if not (isinstance(tool, dict) and tool.get("type") == FUNCTION))
    reasoning = definition.get("reasoning") if isinstance(definition.get("reasoning"), dict) else {}
    rai = definition.get("rai_config") if isinstance(definition.get("rai_config"), dict) else {}
    instructions = definition.get("instructions") if isinstance(definition.get("instructions"), str) else ""
    extra = sorted(_plain(key, WORD) for key in definition if key not in READ_KEYS and key not in ignored)
    return Facts(
        kind=_plain(definition.get("kind"), KIND, ""), model=alias, connection=connection, instructions_sha256=sha256_text(instructions),
        tool_names=tuple(sorted(_plain(tool.get("name"), NAME) for tool in functions)), tools_sha256=tools_digest(functions), foreign_tools=tuple(foreign),
        effort=reasoning.get("effort") if isinstance(reasoning.get("effort"), str) else None,
        rai_policy=rai.get("rai_policy_name") if isinstance(rai.get("rai_policy_name"), str) else None, options=tuple(extra))


@dataclass(frozen=True)
class Difference:
    """One way in which a definition is not what the lock says. `what` is a fixed sentence, with at most eight characters of a hash; it holds no text of the definition."""

    code: str
    what: str

    @property
    def control(self) -> str:
        return CODES[self.code]

    @property
    def certain(self) -> bool:
        return self.code in CERTAIN


def short(sha: object) -> str:
    return sha[:8] if isinstance(sha, str) else "none"


def entry_of(facts: Facts) -> dict:
    """The lock entry of an agent, made from the facts of its definition."""
    return {
        "kind": facts.kind, "model": facts.model, "connection": facts.connection or None, "instructionsSha256": facts.instructions_sha256, "tools": list(facts.tool_names),
        "toolsSha256": facts.tools_sha256, "options": {"reasoningEffort": facts.effort, "raiPolicy": facts.rai_policy},
    }


def compare(entry: Mapping, facts: Facts) -> list[Difference]:
    """Every difference between a lock entry and the facts of a definition. An empty list means that the definition is what the lock says."""
    found: list[Difference] = []
    if facts.kind != entry["kind"]:
        found.append(Difference("kind", f"the kind of agent is not {entry['kind']}"))
    if facts.model != entry["model"]:
        found.append(Difference("model", "the model alias is not the locked one"))
    if (facts.connection or None) != entry["connection"]:
        found.append(Difference("connection", "the model is not reached through the locked connection" if entry["connection"] else "the model is reached through a connection that the lock does not name"))
    if facts.instructions_sha256 != entry["instructionsSha256"]:
        found.append(Difference("instructions", f"the instructions differ (live {short(facts.instructions_sha256)}, locked {short(entry['instructionsSha256'])})"))
    locked_names = tuple(sorted(entry["tools"]))
    if facts.foreign_tools:
        found.append(Difference("tool-kind", f"{len(facts.foreign_tools)} tool{'' if len(facts.foreign_tools) == 1 else 's'} of a kind that is not a function tool: {', '.join(facts.foreign_tools[:4])}"))
    if facts.tool_names != locked_names:
        extra, missing = sorted(set(facts.tool_names) - set(locked_names)), sorted(set(locked_names) - set(facts.tool_names))
        found.append(Difference("tools", f"the tools differ: {len(extra)} that the lock does not list, {len(missing)} that it lists and the definition lacks"
                                         + (f" ({', '.join(extra[:3])})" if extra else "")))
    elif facts.tools_sha256 != entry["toolsSha256"]:
        found.append(Difference("tools", f"the schemas of the tools differ (live {short(facts.tools_sha256)}, locked {short(entry['toolsSha256'])})"))
    options = entry["options"]
    if facts.effort != options["reasoningEffort"]:
        found.append(Difference("effort", "the reasoning effort is not the locked one"))
    if facts.rai_policy != options["raiPolicy"]:
        found.append(Difference("rai", "the guardrail policy is not the locked one"))
    if facts.options:
        found.append(Difference("option", f"{len(facts.options)} option{'' if len(facts.options) == 1 else 's'} that the lock neither pins nor ignores: {', '.join(facts.options[:4])}"))
    return found


# -- the file ---------------------------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Lock:
    agents: Mapping[str, Mapping]
    tools: Mapping[str, Mapping]
    ignored: tuple[str, ...]
    connection: str
    toolbox_sha256: str
    raw: Mapping

    def entry(self, agent: str) -> Mapping | None:
        return self.agents.get(agent)

    @property
    def sha256(self) -> str:
        """The hash of the lock as a whole: what a trace line names when it says which lock was in force."""
        return digest(self.raw)

    def definition_sha256(self, agent: str) -> str:
        """The hash of one agent's whole pinned definition: the version of the agent that the lock stands for."""
        entry = self.agents.get(agent)
        return digest(entry) if entry is not None else ""


def default_path() -> Path:
    return Path(__file__).with_name(FILE_NAME)


def _sha(value: object, where: str) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise LockError(f"{where} is not a SHA-256 in lower-case hexadecimal")
    return value


def validate(document: object) -> Lock:
    """The lock that a document holds, or a LockError. Every part has to be there and to be what it is said to be: a lock that is only nearly right is no lock."""
    if not isinstance(document, dict) or set(document) != {"schema", "connection", "ignoredOptions", "toolbox", "agents", "tools"}:
        raise LockError("the lock does not have exactly the parts schema, connection, ignoredOptions, toolbox, agents and tools")
    if document["schema"] != SCHEMA:
        raise LockError(f"the lock has schema {document['schema']!r}, and this code reads schema {SCHEMA}")
    connection = document["connection"]
    if connection is not None and not (isinstance(connection, str) and WORD.fullmatch(connection)):
        raise LockError("the name of the gateway connection is not a plain word")
    ignored = document["ignoredOptions"]
    if not isinstance(ignored, list) or not all(isinstance(key, str) and WORD.fullmatch(key) for key in ignored):
        raise LockError("ignoredOptions is not a list of plain words")
    toolbox = document["toolbox"]
    if not isinstance(toolbox, dict) or set(toolbox) != {"moduleSha256"}:
        raise LockError("toolbox is not an object with moduleSha256")
    module_sha = _sha(toolbox["moduleSha256"], "toolbox.moduleSha256")
    agents = document["agents"]
    if not isinstance(agents, dict) or not agents or not all(isinstance(name, str) and NAME.fullmatch(name) for name in agents):
        raise LockError("agents is not an object of agents with plain names")
    for name, entry in agents.items():
        keys = {"kind", "model", "connection", "instructionsSha256", "tools", "toolsSha256", "options"}
        if not isinstance(entry, dict) or set(entry) != keys:
            raise LockError(f"the entry of agent {name} does not have exactly the parts {', '.join(sorted(keys))}")
        if not isinstance(entry["kind"], str) or not KIND.fullmatch(entry["kind"]) or not isinstance(entry["model"], str) or not WORD.fullmatch(entry["model"]):
            raise LockError(f"the kind or the model of agent {name} is not a plain word")
        if entry["connection"] is not None and not (isinstance(entry["connection"], str) and WORD.fullmatch(entry["connection"])):
            raise LockError(f"the connection of agent {name} is not a plain word or null")
        _sha(entry["instructionsSha256"], f"{name}.instructionsSha256")
        _sha(entry["toolsSha256"], f"{name}.toolsSha256")
        if not isinstance(entry["tools"], list) or entry["tools"] != sorted(set(entry["tools"])) or not all(isinstance(tool, str) and NAME.fullmatch(tool) for tool in entry["tools"]):
            raise LockError(f"the tools of agent {name} are not a sorted list of different plain names")
        options = entry["options"]
        if not isinstance(options, dict) or set(options) != {"reasoningEffort", "raiPolicy"} or any(value is not None and not (isinstance(value, str) and WORD.fullmatch(value)) for value in options.values()):
            raise LockError(f"the options of agent {name} are not reasoningEffort and raiPolicy, each a plain word or null")
    tools = document["tools"]
    if not isinstance(tools, dict) or not all(isinstance(name, str) and NAME.fullmatch(name) for name in tools):
        raise LockError("tools is not an object of tools with plain names")
    for name, entry in tools.items():
        if not isinstance(entry, dict) or set(entry) != {"schemaSha256", "implementationSha256"}:
            raise LockError(f"the entry of tool {name} does not have exactly the parts schemaSha256 and implementationSha256")
        _sha(entry["schemaSha256"], f"{name}.schemaSha256")
        _sha(entry["implementationSha256"], f"{name}.implementationSha256")
    listed = {tool for entry in agents.values() for tool in entry["tools"]}
    if listed != set(tools):
        raise LockError("the tools that the agents list and the tools of the lock are not the same")
    return Lock(agents=agents, tools=tools, ignored=tuple(ignored), connection=connection or "", toolbox_sha256=module_sha, raw=document)


def load(path: Path | None = None) -> Lock:
    """Reads and checks the lock. Any fault is a LockError: a lock that cannot be read means that no agent runs."""
    where = path or default_path()
    try:
        document = json.loads(where.read_text(encoding="utf-8"))
    except OSError:
        raise LockError(f"the lock {FILE_NAME} cannot be read") from None
    except (ValueError, RecursionError):
        raise LockError(f"the lock {FILE_NAME} is not JSON") from None
    return validate(document)


def build(definitions: Mapping[str, Mapping], implementations: Mapping[str, str], toolbox_module_sha256: str, connection: str | None,
          ignored: Iterable[str] = DEFAULT_IGNORED) -> dict:
    """The lock document for the definitions that the code sends (by agent name), the digests of the code of the tools and the digest of the toolbox's module. It is what
    `tools/agents-lock.py write` saves: the same code always makes the same document."""
    ignored = tuple(ignored)
    agents: dict[str, dict] = {}
    tools: dict[str, dict] = {}
    for name in sorted(definitions):
        definition = definitions[name]
        facts = facts_of(definition, ignored)
        agents[name] = entry_of(facts)
        for tool in definition.get("tools") or []:
            if isinstance(tool, dict) and tool.get("type") == FUNCTION:
                tools[tool["name"]] = {"schemaSha256": digest(schema_of(tool)), "implementationSha256": implementations.get(tool["name"], "")}
    return {"schema": SCHEMA, "connection": connection, "ignoredOptions": sorted(ignored), "toolbox": {"moduleSha256": toolbox_module_sha256},
            "agents": agents, "tools": dict(sorted(tools.items()))}


def stale(lock: Lock, definitions: Mapping[str, Mapping], implementations: Mapping[str, str], toolbox_module_sha256: str) -> list[str]:
    """What differs between the lock and what the code says now, as short sentences that name agents and tools (they are repository names) and hold no hash. Empty: the lock is current."""
    problems: list[str] = []
    if set(definitions) != set(lock.agents):
        problems.append("the agents of the code and of the lock are not the same")
    for name in sorted(set(definitions) & set(lock.agents)):
        for difference in compare(lock.agents[name], facts_of(definitions[name], lock.ignored)):
            problems.append(f"agent {name}: {difference.what}")
    code_tools = {tool["name"]: tool for definition in definitions.values() for tool in definition.get("tools") or [] if isinstance(tool, dict) and tool.get("type") == FUNCTION}
    for name in sorted(set(code_tools) | set(lock.tools)):
        if name not in code_tools:
            problems.append(f"tool {name}: the lock lists it and the code has none")
        elif name not in lock.tools:
            problems.append(f"tool {name}: the code has it and the lock does not list it")
        else:
            if digest(schema_of(code_tools[name])) != lock.tools[name]["schemaSha256"]:
                problems.append(f"tool {name}: its schema changed")
            if implementations.get(name, "") != lock.tools[name]["implementationSha256"]:
                problems.append(f"tool {name}: the code that runs it changed")
    if toolbox_module_sha256 != lock.toolbox_sha256:
        problems.append("the module of the tools changed")
    return problems
