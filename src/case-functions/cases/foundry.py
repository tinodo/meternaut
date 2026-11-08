"""Microsoft Foundry Agent Service, over REST: make sure an agent exists in the project and run it, with function tools that this app executes.

Read on Microsoft Learn on 2026-11-06 and not tried on the service. The token is for the resource https://ai.azure.com. The /agents calls carry api-version=v1, the
/openai/v1 calls carry none. Agents: GET /agents/NAME (a 404 is taken as absent), POST /agents (a 409 is taken as: another run made it), POST /agents/NAME/versions. A
version is immutable and has metadata (16 pairs, values up to 512 characters): the hash of the definition is kept there, because an agent holds 1,000 versions at most.
Conversations: POST /openai/v1/conversations and DELETE /openai/v1/conversations/ID. A run: POST /openai/v1/responses with {agent_reference, conversation, input}. The
article on function calling writes the key `agent` and the REST reference `agent_reference`: the reference is sent first, and if the first response is answered with an
HTTP 400 or 422 that is not about the model (MODEL_TROUBLE), `agent` is sent once and kept; if that is answered that `agent` is deprecated, the first answer is raised and
`agent_reference` stays (the first real run, 2026-11-08, showed that `agent_reference` is the key). A definition may hold `reasoning: {"effort": ...}` (AgentSpec.reasoning_effort).
An answer has status, error {code, message}, output items (message, function_call, reasoning)
and usage {input_tokens, output_tokens}. All the function calls of an answer are answered in one input list of function_call_output items. A run expires 10 minutes after
it was made. Structured output (text.format) is set on the definition or the response: this module sets none. A function tool has strict false: its default is true.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import re
import socket
from dataclasses import dataclass, field
from typing import Callable, Iterable
from urllib.parse import urlsplit

from .http import FOUNDRY_AGENT_NAME, FOUNDRY_CONVERSATION_ID, FOUNDRY_ENDPOINT, Client, HttpError, Refused
from .identity import IdentityError
from .redact import Redactor

LOG = logging.getLogger("meternaut.foundry")

RESOURCE = "https://ai.azure.com"
API = "api-version=v1"
HASH_KEY = "meternaut_spec_sha256"
RESPONSE_TIMEOUT = 180
CLEANUP_TIMEOUT = 15
WORDS_LIMIT = 200
MAX_NOTES = 20
# A list of the project (agents, connections) is read in pages of this many, and at most this many pages: an agent or a connection beyond them is not looked at, and the answer says so.
LIST_PAGE = 100
LIST_PAGES = 5
CURSOR = re.compile(r"[A-Za-z0-9_:.-]{1,128}")
TOOL_FAILED = '{"error":"tool-failed"}'
BAD_ARGUMENTS = '{"error":"bad-arguments"}'
CUT_NOTE = " [cut: the answer was longer than the limit]"
# What a run says when the agent ends with no text and no tool call: the harness counts it as a failure of the run (cases/harness.py), so the words are one constant.
NO_TEXT = "the answer holds no text"
BUDGET_USED_UP = '{"error":"budget-used-up"}'
GRACE_ROUNDS = 3  # after the first answer that says so, the agent has this many more rounds to give its text
# A call that may already have been carried out (a creation, a run) is repeated only when the service says "not now".
NOT_NOW = {"retry_statuses": frozenset({429, 503}), "retry_network": False}
# A model that has used the tokens of its deployment for the minute says "not now" (HTTP 429) to the next step of a run, and the first real runs showed that it says
# it without a Retry-After and that 1 to 4 seconds is not enough to get the tokens back. A step of a run is therefore repeated up to RATE_RETRIES times, after 8 seconds
# (with jitter), then 16, then 30 at most, and a Retry-After of more than RATE_WAIT_MAX seconds is an error. The pauses stay inside the time of the run. The 429 comes
# before the model has produced anything, so the conversation is unchanged and the same input is sent again.
RATE_RETRIES = 6
RATE_BACKOFF = 8.0
RATE_BACKOFF_MAX = 30.0
RATE_WAIT_MAX = 90.0
# The part of the time of a run after which the tool calls of the agent are refused like a call beyond the budget: it then gives the answer that it has, and a run that
# is slowed by the rate of its model still ends with that answer before its hard limit.
SOFT_TIME_SHARE = 0.7
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))  # RFC 1918
AGENT_NAME = re.compile(FOUNDRY_AGENT_NAME)
CONVERSATION_ID = re.compile(FOUNDRY_CONVERSATION_ID)
VERSION = re.compile(r"[A-Za-z0-9._-]{1,64}")
TOOL_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
KIND = re.compile(r"[a-z_]{1,40}")
# A kind of connection or of credential as the data plane names it (AzureOpenAI, ApiKey, ProjectManagedIdentity, ...): plain words, and nothing else is kept of an answer.
KIND_WORD = re.compile(r"[A-Za-z_]{1,40}")
STATUSES = frozenset({"failed", "in_progress", "cancelled", "queued", "incomplete"})
# The key of the agent reference in the body of a response: the REST reference writes the first, the article on function calling the second. The service may take only
# one of them, and the words that it uses to refuse the other are not relied on, but for the two kinds of answer that follow: see Foundry._respond. A service refuses an
# unknown field with a 400, and some stacks with a 422.
AGENT_KEYS = ("agent_reference", "agent")
FIRST_CALL_REFUSALS = frozenset({400, 422})
# An answer about the model, its reasoning effort or its function tools is not about the key, and the call is not made again with the other key. The first real run (2026-11-08)
# was refused with the code `model_error` ("Function tools with reasoning_effort are not supported for the model in /v1/chat/completions"), and the call that was made again
# with `agent` was told that this key is deprecated: the second answer hid the first, which was the real one. Such an answer is not about the route either (route_failure).
MODEL_TROUBLE = re.compile(r"\bmodel_error\b|reasoning[_ ]effort|function[_ ]tools?")
# What the service says of the other key when the first one was the right one ("The 'agent' property is deprecated. Use 'agent_reference' instead"): the first answer is then raised.
KEY_DEPRECATED = re.compile(r"\bdeprecated\b.*\bagent_reference\b")
# The effort that a definition asks the model to reason with: the service knows the words (none, minimal, low, medium, high, xhigh, max), this app only keeps to one plain word.
EFFORT = re.compile(r"[a-z]{1,16}")
# The model of an agent may be named `<connection>/<model>`: it is then called through a connection of the project, which for this project is the AI Gateway (docs/proposals/08-ai-gateway.md, step 2).
# A call of a run that such a model fails is explained in fixed words that a person can act on (FoundryError.route), and only when the service's own status and words say that the failure is about the
# route: a call that the service refuses for another reason keeps its own words and gets no explanation. What the Agent Service says when the gateway refuses it is not known (nothing of this has run), so the
# cause is found from the HTTP status of the answer and from words in the code and the message of the error, and an answer that none of them fits is left as it was.
ROUTE_PURPOSES = frozenset({"response", "function output", "create agent", "new version"})
CONNECTION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
ROUTE_CODE = re.compile(r"[A-Za-z0-9._-]{1,24}")


@dataclass(frozen=True)
class RouteCause:
    """What one kind of answer means for a call through a connection. `statuses` and `words` say it: the HTTP status of the call, or words in the code and the message of the error. `proof` is what the
    words must also hold when the answer carries an HTTP status, so that a refusal of the app's own call (a 401 or a 403 for the app's token, a 404 for an agent) is not taken for the route's, and
    `proof_in_response` asks for it in the error object of a response that completed too. `cause` and `check` are the fixed words of the explanation."""

    statuses: frozenset
    words: re.Pattern
    proof: re.Pattern | None
    proof_in_response: bool
    cause: str
    check: str


ROUTE_CAUSES = (
    RouteCause(frozenset({401}), re.compile(r"\b401\b|unauthori[sz]ed|unauthenticated|invalid[ _]?token|audience|authentication (?:failed|error)"),
               re.compile(r"gateway|connection|upstream|audience"), False,
               "the gateway did not accept the token of the project", "Check the audience and the service principal."),
    RouteCause(frozenset({403}), re.compile(r"\b403\b|forbidden|permission[ _]?denied|not authori[sz]ed|authori[sz]ation|access denied"),
               re.compile(r"gateway|connection|upstream"), False,
               "the gateway refused the project's identity", "Check its role AI Gateway Models User on the gateway."),
    RouteCause(frozenset({404}), re.compile(r"\b404\b|not[ _]?found|does not exist|no such|unknown model"), re.compile(r"model|deployment|connection|gateway|alias"), True,
               "the connection or the model was not found", "Check the target and the model names of the connection."),
    RouteCause(frozenset({429}), re.compile(r"\b429\b|rate[ _]?limit|too many requests|throttl|quota"), None, False,
               "the call was told to wait", "Check the limits of the gateway and of the model."),
    RouteCause(frozenset({502, 503, 504}), re.compile(r"timed? ?out|unreachable|could not connect|connection refused|bad gateway|service unavailable|gateway timeout"), None, False,
               "the gateway did not answer well", "Run aigateway-check and read the status of the Agent Service."),
    RouteCause(frozenset({424}), re.compile(r"(?!)"), None, False, "the call to the gateway failed", "Read the log of the gateway."),
    RouteCause(frozenset(), re.compile(r"connection|gateway|upstream"), None, False, "the connection or the gateway cannot be used", "Check the connection in the project."),
)


def connection_of(model: object) -> str:
    """The connection that a model name goes through: the part before the slash of `<connection>/<model>`, and "" for a plain deployment name or a name that is not shaped like one."""
    name, slash, rest = model.partition("/") if isinstance(model, str) else ("", "", "")
    return name if slash and rest and CONNECTION_NAME.fullmatch(name) else ""


def route_failure(model: object, purpose: str, status: int | None, code: str, words: str, dns: str | None = None) -> str:
    """The fixed words for a failed call of an agent whose model goes through a connection, or "" when the model has none, the call is not one that the route can fail, or the answer says nothing
    about the route. They name the connection, say what happened, quote the HTTP status and the code of the service when there are some, and say what to check; they hold nothing else of the answer.

    `status` is the HTTP status of the call, or None for an error object inside a response that completed. A 403 or a 404 of a call whose host name does not lead to a private address (`dns`) may be a
    failure before the project's endpoint was reached, and is left to the text that says so."""
    connection = connection_of(model)
    if not connection or purpose not in ROUTE_PURPOSES or (status in (403, 404) and dns not in (None, "private")):
        return ""
    text = f"{code} {words}".lower()
    if MODEL_TROUBLE.search(text):  # the model refused the call: the answer says so in its own words, and the route is not at fault
        return ""
    for rule in ROUTE_CAUSES:
        if not ((status in rule.statuses) or rule.words.search(text)):
            continue
        if rule.proof is not None and (status is not None or rule.proof_in_response) and not rule.proof.search(text):
            continue
        detail = [part for part in (f"HTTP {status}" if status else "", f"code {code}" if code else "") if part]
        return f"the model call through the connection {connection} failed: {rule.cause}" + (f" ({', '.join(detail)})" if detail else "") + f". {rule.check}"
    return ""


class FoundryError(Exception):
    """The service gave no usable answer. The text says what was asked and what went wrong: the HTTP status, a fact about the DNS of the host when that may be the
    cause, and the code and the message that the service itself gave (redacted and cut). It never holds a token, a request, an answer of a tool or the text of a model.
    `status` is the HTTP status when there was one, and `words` the code and the message of the service as they are in the text. `code` is the service's own code when it is
    a plain token. `route` is the fixed explanation of route_failure when the model of the agent goes through a connection and the answer is about that route, and "" otherwise.
    `partial` is what the run had come to when it failed (its calls and its tokens)."""

    status: int | None = None
    words: str = ""
    code: str = ""
    route: str = ""
    partial: AgentRun | None = None


@dataclass(frozen=True)
class FunctionTool:
    """A tool that the agent may ask for and that this app runs: a name, what it is for, and the JSON schema of its arguments."""

    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class AgentSpec:
    """The definition of a prompt agent. A change to it makes a new version of the agent in the project. `reasoning_effort` is the effort that the model is asked to reason
    with, sent as `reasoning.effort` of the definition: the word "none" is sent as the effort none, and None (the default) leaves it out."""

    name: str
    description: str
    model: str
    instructions: str
    tools: tuple[FunctionTool, ...] = ()
    reasoning_effort: str | None = None


@dataclass
class AgentRun:
    """What one run of an agent came to: its last text, the tools that it asked for, and the tokens that it used."""

    text: str
    # One dict per tool call that the agent asked for: name, arguments, ok, chars. `cut` is True when the answer was cut. `refused` is True when the budget of tool
    # calls or the soft time was used up: the handler was not called and the agent was told {"error":"budget-used-up"}.
    calls: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    responses: int = 0
    # True when a call was refused because the soft time of the run was used up (and not the budget of calls).
    out_of_time: bool = False


# (tool name, arguments) -> the result as a JSON string that holds typed values only. It never raises.
ToolHandler = Callable[[str, dict], str]


def host_kind(host: str, resolve: Callable[..., Iterable] = socket.getaddrinfo) -> str:
    """Where a host name leads: "private" when every address of it is in an RFC 1918 range, "public" when any address is outside them (a loopback or a link-local
    address too), "unresolved" when it does not resolve or the answer cannot be read. It names no address. `resolve` has the signature of socket.getaddrinfo."""
    try:
        addresses = [ipaddress.ip_address(str(answer[4][0]).split("%")[0]) for answer in resolve(host, 443, type=socket.SOCK_STREAM)]
    except Exception:  # noqa: BLE001 (any failure of the lookup means that the name did not resolve)
        return "unresolved"
    if not addresses:
        return "unresolved"
    return "private" if all(_is_private(address) for address in addresses) else "public"


def _is_private(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.version == 4 and any(address in network for network in PRIVATE_NETWORKS)


def _plain(text: str) -> str:
    """One line of printable characters: a space for white space, and nothing for any other control character."""
    return " ".join("".join(c if c.isprintable() else (" " if c.isspace() else "") for c in text).split())


def _payload(spec: AgentSpec) -> dict:
    """What the service is sent for a spec, without the name and the metadata. It is checked here, because the name becomes a part of an address."""
    tools = spec.tools if isinstance(spec.tools, (tuple, list)) else None
    if not isinstance(spec.name, str) or not AGENT_NAME.fullmatch(spec.name):
        problem = "the name of the agent"
    elif not isinstance(spec.model, str) or not spec.model.strip():
        problem = "the model"
    elif not isinstance(spec.instructions, str):
        problem = "the instructions"
    elif not isinstance(spec.description, str) or len(spec.description) > 512:
        problem = "the description (a text of at most 512 characters)"
    elif tools is None or len(tools) > 128 or not all(isinstance(t, FunctionTool) for t in tools):
        problem = "the tools (at most 128 function tools)"
    elif not all(isinstance(t.name, str) and TOOL_NAME.fullmatch(t.name) for t in tools) or len({t.name for t in tools}) != len(tools):
        problem = "the names of the tools (each different, letters, digits, _ and - only)"
    elif not all(isinstance(t.description, str) and isinstance(t.parameters, dict) for t in tools):
        problem = "the description or the parameters of a tool"
    elif spec.reasoning_effort is not None and not (isinstance(spec.reasoning_effort, str) and EFFORT.fullmatch(spec.reasoning_effort)):
        problem = "the reasoning effort (one word of lower-case letters, or None to leave it out)"
    else:
        definition: dict = {"kind": "prompt", "model": spec.model, "instructions": spec.instructions}
        if tools:
            # strict is set: its default is true (Learn, FunctionTool.Strict), and a strict schema must list every property as required.
            definition["tools"] = [{"type": "function", "name": t.name, "description": t.description, "parameters": t.parameters, "strict": False} for t in tools]
        if spec.reasoning_effort is not None:
            definition["reasoning"] = {"effort": spec.reasoning_effort}  # PromptAgentDefinition.reasoning (Learn, azure-ai-projects): Reasoning.effort
        return {"definition": definition, **({"description": spec.description} if spec.description else {})}
    raise FoundryError(f"Foundry: the definition of the agent is not valid: {problem}")


def definition_of(spec: AgentSpec) -> dict:
    """The `definition` that this app sends to the service for a spec: the one that the lock of the agents pins (cases/lockfile.py) and that the harness compares with the stored one."""
    return _payload(spec)["definition"]


class Foundry:
    """Calls the Foundry Agent Service of one project. A client belongs to one run: `run` and `_call` set its deadline and its transport for as long as they work.
    `notes` holds short texts about problems that stopped nothing (a conversation that could not be deleted, a key of the agent reference that was refused).
    `resolve` is the lookup of a host name."""

    def __init__(self, endpoint: str, client: Client, token: Callable[[str], str], redact: Redactor) -> None:
        text = endpoint.removesuffix("/") if isinstance(endpoint, str) else ""
        if not FOUNDRY_ENDPOINT.fullmatch(text):
            raise FoundryError("Foundry: the endpoint of the project is not https://<account>.services.ai.azure.com/api/projects/<project>")
        self.endpoint, self.client, self.token, self.redact = text, client, token, redact
        self.host = urlsplit(text).netloc
        self.resolve: Callable[..., Iterable] = socket.getaddrinfo
        self.notes: list[str] = []
        self._dns: str | None = None
        self._key = AGENT_KEYS[0]  # the key of the agent reference that a response is sent with
        self._key_open = True  # until the service has answered a response: only that first answer may send the client to the other key
        self._models: dict[str, str] = {}  # the model of each agent that this client has made sure of, by name
        self._model: str | None = None  # the model of the agent that the calls in hand are for

    def ensure_agent(self, spec: AgentSpec) -> str:
        """Creates the agent when it is not there and a new version when its definition differs. Returns "name:version".

        The definition is compared by its hash, which the version keeps in its metadata: an agent holds 1,000 versions at most, and the service may add defaults to
        what it stores, so the stored definition itself is not compared. It takes one GET when nothing changed. A 409 on the creation (another run made the agent a
        moment ago) is no failure: the agent is read and compared like any agent."""
        payload = _payload(spec)
        self._models[spec.name], self._model = spec.model, spec.model
        try:
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        except (TypeError, ValueError):
            raise FoundryError("Foundry: the definition of the agent cannot be written as JSON") from None
        metadata = {HASH_KEY: digest}
        saved = self._call("GET", f"/agents/{spec.name}?{API}", purpose="read agent", gone_ok=True)
        if saved is None:
            conflict = None
            try:
                created = self._call("POST", f"/agents?{API}", {"name": spec.name, **payload, "metadata": metadata}, purpose="create agent", once=True)
            except FoundryError as error:
                if error.status != 409:
                    raise
                conflict = error
            else:
                version = self._version(created, spec.name, "create agent", of_agent=True)["version"]
                LOG.info("Foundry agent %s: made, version %s", spec.name, version)
                return f"{spec.name}:{version}"
            # Another run made the agent a moment ago. It is read now and compared like any agent: it is the same, or it gets a new version.
            saved = self._call("GET", f"/agents/{spec.name}?{API}", purpose="read agent", gone_ok=True)
            if saved is None:
                raise conflict
            LOG.info("Foundry agent %s: made by another run", spec.name)
        latest = self._version(saved, spec.name, "read agent", of_agent=True)
        kept = latest.get("metadata")
        if isinstance(kept, dict) and kept.get(HASH_KEY) == digest:
            return f"{spec.name}:{latest['version']}"
        made = self._call("POST", f"/agents/{spec.name}/versions?{API}", {**payload, "metadata": metadata}, purpose="new version", once=True)
        version = self._version(made, spec.name, "new version", of_agent=False)["version"]
        LOG.info("Foundry agent %s: new version %s", spec.name, version)
        return f"{spec.name}:{version}"

    def read_agent(self, name: str) -> dict | None:
        """The latest version of an agent as the service stores it: {name, version, metadata, definition, ...}, or None when there is no agent of that name. It is one read, and the
        harness makes it right before a run, to hold the stored definition against the lock."""
        if not isinstance(name, str) or not AGENT_NAME.fullmatch(name):
            raise FoundryError("Foundry: the name of the agent is not valid")
        saved = self._call("GET", f"/agents/{name}?{API}", purpose="read agent", gone_ok=True)
        return None if saved is None else self._version(saved, name, "read agent", of_agent=True)

    def list_agents(self) -> tuple[list[dict], bool]:
        """Every agent of the project as {"name", "latest"}: the name (None when it is not a name that this app accepts) and the latest version as the service stores it (None when the
        answer has none). The second value is True when the list goes on after the pages that were read. Only the drift check lists agents, with a client of its own."""
        found: list[dict] = []
        after = None
        for _ in range(LIST_PAGES):
            document = self._call("GET", f"/agents?{API}&limit={LIST_PAGE}" + (f"&after={after}" if after else ""), purpose="list agents")
            page = document.get("data") if isinstance(document.get("data"), list) else document.get("value") if isinstance(document.get("value"), list) else []
            for item in page:
                if not isinstance(item, dict):
                    found.append({"name": None, "latest": None})
                    continue
                versions = item.get("versions")
                latest = versions.get("latest") if isinstance(versions, dict) else None
                name = item.get("name")
                found.append({"name": name if isinstance(name, str) and AGENT_NAME.fullmatch(name) else None, "latest": latest if isinstance(latest, dict) else None})
            last = document.get("last_id")
            if document.get("has_more") is not True or not isinstance(last, str) or not CURSOR.fullmatch(last):
                return found, False
            after = last
        return found, True

    def list_connections(self) -> tuple[list[dict], bool]:
        """Every connection of the project as the data plane shows it, without credentials: {"name", "type", "target", "credentials"} with plain words only (the kind of credential, never
        one). A name or a word that this app does not accept is shown as None. The second value is True when the list goes on after the pages that were read."""
        found: list[dict] = []
        path = f"/connections?{API}"
        for _ in range(LIST_PAGES):
            document = self._call("GET", path, purpose="list connections")
            page = document.get("value") if isinstance(document.get("value"), list) else document.get("data") if isinstance(document.get("data"), list) else []
            for item in page:
                item = item if isinstance(item, dict) else {}
                credentials = item.get("credentials") if isinstance(item.get("credentials"), dict) else {}
                found.append({"name": item.get("name") if isinstance(item.get("name"), str) and CONNECTION_NAME.fullmatch(item["name"]) else None,
                              "type": item.get("type") if isinstance(item.get("type"), str) and KIND_WORD.fullmatch(item["type"]) else None,
                              "target": item.get("target") if isinstance(item.get("target"), str) and len(item["target"]) <= 300 else None,
                              "credentials": credentials.get("type") if isinstance(credentials.get("type"), str) and KIND_WORD.fullmatch(credentials["type"]) else None})
            link = document.get("nextLink")
            if not isinstance(link, str) or not link.startswith(self.endpoint + "/"):
                return found, False
            path = link[len(self.endpoint):]
        return found, True

    def run(self, agent: str, user_input: str, handler: ToolHandler | None = None, *, max_calls: int = 20, max_seconds: float | None = None,
            stop: Callable[[AgentRun], str | None] | None = None) -> AgentRun:
        """Runs the agent on one input, answers each function call of it with `handler`, and returns when the agent gives its text.

        `agent` is what ensure_agent returned ("name:version": that version is run) or a name. The calls of one answer are all made and answered in one request.
        Arguments that are not a JSON object are not given to the handler: the agent is told {"error":"bad-arguments"}. A handler that raises, or that does not give a
        string, makes the answer {"error":"tool-failed"}. An answer longer than cases.toolbox.MAX_RESULT_CHARS is cut and says so.

        `max_calls` is a soft budget. That many calls are run (one that failed counts). Every call after them is not given to the handler: it is answered
        {"error":"budget-used-up"} and recorded with refused: True, and the agent has GRACE_ROUNDS (3) more rounds to give its text. The same is done with every call
        that the agent asks for after SOFT_TIME_SHARE (70%) of `max_seconds` has passed (the result then has out_of_time True), so that a run that was slowed down, by the
        rate of its model for instance, still gives its answer before the hard limit. A FoundryError is raised when it
        still asks for a tool call after those rounds, when `max_seconds` pass (that limit is hard, also while a tool works), or when the service gives no usable answer.
        What the run had gathered is in the `partial` of every FoundryError of a run. The conversation is deleted in every case, after the time is used up too.

        The key of the agent reference is `agent_reference` (the REST reference). If the first response that the service answers in the life of this client is an
        HTTP 400 or 422 that is not about the model, its reasoning effort or its function tools, it is made again, once, with `agent` (the article on function calling),
        and the key that worked is kept for every later call. That first call carries no function output, so repeating it is safe. No other call and no other answer
        starts that. A second failure is raised, and so is the first answer when the second one says that `agent` is deprecated: `agent_reference` then stays.

        `stop` is the brake of the harness (cases/harness.py): it is called with what the run has come to before every request to the model, the first one too, and a reason that it
        returns (plain words) ends the run with a FoundryError. A `stop` that raises ends the run too: a brake that cannot decide is a brake that holds."""
        reference = self._reference(agent)
        self._model = self._models.get(reference["name"])
        if not isinstance(user_input, str) or not user_input.strip():
            raise FoundryError("Foundry: the run has no input")
        if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls < 0:
            raise FoundryError("Foundry: max_calls is not a whole number from 0 up")
        if max_seconds is not None and (isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) or not max_seconds > 0):
            raise FoundryError("Foundry: max_seconds is not a number above 0")
        result = AgentRun(text="")
        now = self.client.monotonic
        began = now()
        deadline = None if max_seconds is None else began + max_seconds
        soft = None if max_seconds is None else began + SOFT_TIME_SHARE * max_seconds
        saved = self.client.deadline
        if deadline is not None:
            self.client.deadline = deadline if saved is None else min(saved, deadline)
        conversation = None
        try:
            conversation = self._conversation(user_input)
            pending: list[dict] = []
            purpose = "response"
            made = refused = told = 0  # tool calls that were run, tool calls that were refused for the budget, and answers that held a refused call
            while True:
                if deadline is not None and now() >= deadline:
                    raise self._error(f"Foundry run stopped: the time allowed ({max_seconds:g} seconds) was used up after {made} tool calls"
                                      + (f" and {refused} that were refused" if refused else ""))
                if stop is not None:
                    try:
                        why = stop(result)
                    except Exception:  # noqa: BLE001 (a brake that cannot decide holds)
                        why = "the stop check failed"
                    if why:
                        raise self._error(f"Foundry run stopped by the harness: {why}")
                document = self._respond(reference, conversation, pending, purpose)
                result.responses += 1
                self._count(result, document, purpose)
                output = self._output(document, purpose)
                calls = self._calls(output, purpose)
                if not calls:
                    result.text = self._text(output, purpose)
                    return result
                if handler is None:
                    raise self._error("Foundry run stopped: the agent asked for a tool call and no handler was given")
                before, pending = refused, []
                for each in calls:
                    late = soft is not None and now() >= soft
                    if made < max_calls and not late:
                        pending.append(self._answer(each, handler, result))
                        made += 1
                    else:
                        pending.append(self._refuse(each, result))
                        refused += 1
                        if late and made < max_calls:
                            result.out_of_time = True
                if refused > before:
                    told += 1
                    if told > GRACE_ROUNDS:
                        spent = (f"the time for tool calls ({SOFT_TIME_SHARE * max_seconds:g} seconds) was used up" if result.out_of_time
                                 else f"the budget of {max_calls} tool calls was used up")
                        raise self._error(f"Foundry run stopped: {spent} and the agent still asked for a tool call after {GRACE_ROUNDS} more rounds, and gave no text")
                purpose = "function output"
        except FoundryError as error:
            error.partial = result
            raise
        finally:
            self._forget(conversation, saved)

    def _respond(self, reference: dict, conversation: str, pending: list[dict], purpose: str) -> dict:
        """One POST of /responses. The first one that the service answers in the life of this client is made again, once, with the other key of the agent reference,
        when the service answers it with an HTTP 400 or 422 that is not about the model: the REST reference and the article on function calling write the key
        differently, and the service may take only one. An answer about the model, its reasoning effort or its function tools (MODEL_TROUBLE) is raised as it is,
        because the other key cannot mend it. The key that worked is kept. That first call carries no function output (it is the one that opens the conversation), so
        repeating it is safe, and no function output is ever sent twice. A second failure is raised, and a note says which key was refused and why. But when the second
        answer says that the other key is deprecated (KEY_DEPRECATED), the first key was the right one: the first answer is the real one, it is raised, and the key stays."""
        first, key = self._key_open and not pending, self._key
        refused = None
        try:
            document = self._post_response(key, reference, conversation, pending, purpose)
        except FoundryError as error:
            if error.status is not None:
                self._key_open = False
            if not (first and error.status in FIRST_CALL_REFUSALS) or MODEL_TROUBLE.search(f"{error.code} {error.words}".lower()):
                raise
            refused = error
        else:
            self._key_open = False
            return document
        other = AGENT_KEYS[1 - AGENT_KEYS.index(key)]
        reason = refused.words or "no reason given"
        try:
            document = self._post_response(other, reference, conversation, pending, purpose)
        except FoundryError as second:
            if KEY_DEPRECATED.search(second.words.lower()):
                self._note(f"Foundry {purpose}: the service says that the key {other} is deprecated, so {key} stays, and the first answer is the real one ({reason})")
                raise refused from None
            self._note(f"Foundry {purpose}: the key {key} was refused ({reason}), and {other} failed too")
            raise
        self._key = other
        self._note(f"Foundry {purpose}: the key {key} was refused ({reason}); {other} is used from now on")
        return document

    def _post_response(self, key: str, reference: dict, conversation: str, pending: list[dict], purpose: str) -> dict:
        body = {key: reference, "conversation": conversation, "input": pending}
        return self._call("POST", "/openai/v1/responses", body, purpose=purpose, timeout=RESPONSE_TIMEOUT, once=True, patient=True)

    # -- the calls ------------------------------------------------------------------------------------------------------------------------------
    def _call(self, method: str, path: str, body: object = None, *, purpose: str, timeout: float = 30, retries: int = 2, once: bool = False, gone_ok: bool = False,
              parse: bool = True, patient: bool = False) -> dict | None:
        """One call to the project. Returns the answer as a JSON object ({} when `parse` is off), or None for a 404 when `gone_ok`. `once` is for a call that may have
        been carried out when its answer did not arrive (a creation, a run): it is repeated only when the service says "not now". `patient` (a step of a run) waits
        for the model to have tokens again: see RATE_RETRIES."""
        try:
            token = self.token(RESOURCE)
        except IdentityError as error:
            raise self._error(f"Foundry {purpose} failed: no token could be had for the service ({self.redact(error)})") from None
        self.redact.add(token)
        seen: list[tuple[int, bytes]] = []
        not_now = [0]
        transport = self.client.transport

        # The client keeps only a cut text of an error body. The answers of this call are kept here, so that the error object of the last one can be read from the body.
        def keep(*call):  # noqa: ANN002, ANN202
            seen.clear()
            answer = transport(*call)
            seen.append((answer[0], answer[2]))
            if answer[0] in NOT_NOW["retry_statuses"]:
                not_now[0] += 1
            return answer

        waits = ({"retries": RATE_RETRIES, "backoff": RATE_BACKOFF, "backoff_max": RATE_BACKOFF_MAX, "retry_after_max": RATE_WAIT_MAX} if patient
                 else {"retries": retries})

        self.client.transport = keep
        try:
            response = self.client.request(method, f"{self.endpoint}{path}", headers={"Authorization": f"Bearer {token}"}, body=body, timeout=timeout, **waits,
                                           **(NOT_NOW if once else {}))
        except HttpError as error:
            if gone_ok and error.status == 404:
                return None
            raise self._failure(purpose, error, seen[0][1] if seen and seen[0][0] == error.status else b"") from None
        except Refused as error:
            raise self._error(f"Foundry {purpose} failed: {error}") from None
        finally:
            self.client.transport = transport
        if not_now[0] and patient:
            self._note(f"Foundry {purpose}: the service said not now (HTTP 429 or 503) {not_now[0]} time{'' if not_now[0] == 1 else 's'}, and the call was made again after a pause")
        if not parse:
            return {}
        try:
            document = response.json()
        except (HttpError, RecursionError):
            raise self._error(f"Foundry {purpose} failed: the answer is not JSON", response.status) from None
        if not isinstance(document, dict):
            raise self._error(f"Foundry {purpose} failed: the answer is not a JSON object", response.status)
        return document

    def _failure(self, purpose: str, error: HttpError, answer: bytes) -> FoundryError:
        """The error of a call that failed: what was asked, the status, the DNS fact when the cause may be there, and the words of the service."""
        deadline = error.status == 0 and "the deadline of the run was reached" in str(error)
        if error.status:
            parts = [f"Foundry {purpose} failed: HTTP {error.status}"]
        else:
            parts = [f"Foundry {purpose} failed: " + ("the time allowed was used up" if deadline else "no answer (the connection failed or timed out)")]
        if error.status in (0, 403, 404) and not deadline:
            if self._dns is None:
                self._dns = host_kind(self.host, self.resolve)
            parts.append(f"DNS of the endpoint host: {self._dns}")
        try:
            document = json.loads(answer.decode("utf-8"))
        except (ValueError, RecursionError):
            document = None
        words = self._words(document.get("error") if isinstance(document, dict) else None)
        if words:
            parts.append(words)
        failure = self._error("; ".join(parts), error.status or None, words)
        failure.code = self._code(document.get("error") if isinstance(document, dict) else None)
        failure.route = route_failure(self._model, purpose, failure.status, failure.code, words, self._dns)
        return failure

    def _words(self, error: object) -> str:
        """The code and the message of an error object of the service. They are its own words: they lose every control character, go through the redactor and
        then are cut to 200 characters (in that order, so that a token on the cut is redacted as a whole)."""
        if not isinstance(error, dict):
            return ""
        parts = []
        for key in ("code", "message"):
            value = error.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                value = str(value)
            if isinstance(value, str):
                parts.append(_plain(self.redact(value[:20000])))
        return self.redact(": ".join(part for part in parts if part))[:WORDS_LIMIT]

    def _code(self, error: object) -> str:
        """The code of an error object of the service when it is a plain token (letters, digits and . _ -, at most 24) that the redactor leaves alone, and "" otherwise. It is the one part of an
        answer that the fixed words of route_failure quote."""
        value = error.get("code") if isinstance(error, dict) else None
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        return value if isinstance(value, str) and ROUTE_CODE.fullmatch(value) and self.redact(value) == value else ""

    def _error(self, text: str, status: int | None = None, words: str = "") -> FoundryError:
        error = FoundryError(self.redact(text))
        error.status, error.words = status, words
        return error

    def _note(self, text: str) -> None:
        text = self.redact(text)
        LOG.warning(text)
        if len(self.notes) < MAX_NOTES:
            self.notes.append(text)

    def _conversation(self, user_input: str) -> str:
        item = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": user_input}]}
        created = self._call("POST", "/openai/v1/conversations", {"items": [item]}, purpose="create conversation", once=True)
        conversation = created.get("id")
        if not isinstance(conversation, str) or not CONVERSATION_ID.fullmatch(conversation):
            raise self._error("Foundry create conversation failed: the answer holds no conversation id that this app accepts")
        return conversation

    def _forget(self, conversation: str | None, deadline: float | None) -> None:
        """Puts the deadline of the client back and deletes the conversation. The delete is made when the time of the run is used up too, and it never hides how
        the run ended: a delete that fails is a note and a log line."""
        self.client.deadline = None
        try:
            if conversation:
                self._call("DELETE", f"/openai/v1/conversations/{conversation}", purpose="delete conversation", timeout=CLEANUP_TIMEOUT, retries=1, gone_ok=True,
                           parse=False)
        except FoundryError as error:
            self._note(str(error))
        except Exception as error:  # noqa: BLE001 (a clean-up never hides how the run ended)
            self._note(f"Foundry delete conversation failed: {type(error).__name__}")
        finally:
            self.client.deadline = deadline

    # -- what an answer holds ---------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _reference(agent: str) -> dict:
        name, colon, version = agent.partition(":") if isinstance(agent, str) else ("", "", "")
        if not AGENT_NAME.fullmatch(name) or (colon and not VERSION.fullmatch(version)):
            raise FoundryError("Foundry: the agent to run is not a name or name:version")
        return {"type": "agent_reference", "name": name, **({"version": version} if colon else {})}

    def _version(self, document: dict, name: str, purpose: str, *, of_agent: bool) -> dict:
        """The version object of an answer: an agent holds it as versions.latest, and the answer of a new version is it. Its version is a string."""
        if of_agent:
            versions = document.get("versions")
            document = versions.get("latest") if isinstance(versions, dict) else None
        version = document.get("version") if isinstance(document, dict) else None
        if isinstance(version, int) and not isinstance(version, bool):
            version = str(version)
        if not isinstance(document, dict) or document.get("name") != name or not isinstance(version, str) or not VERSION.fullmatch(version):
            raise self._error(f"Foundry {purpose} failed: the answer holds no version of the agent that this app can read")
        return {**document, "version": version}

    def _count(self, result: AgentRun, document: dict, purpose: str) -> None:
        usage = document.get("usage")
        if usage is None:
            return
        numbers = [usage.get(key, 0) for key in ("input_tokens", "output_tokens")] if isinstance(usage, dict) else [-1]
        if any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in numbers):
            raise self._error(f"Foundry {purpose} failed: the answer reports a usage that is not valid")
        result.input_tokens += numbers[0]
        result.output_tokens += numbers[1]

    def _output(self, document: dict, purpose: str) -> list[dict]:
        """The output items of an answer that completed. An answer that failed, was cut short or is not done yet is an error."""
        if document.get("error"):
            words = self._words(document["error"])
            failure = self._error(f"Foundry {purpose} failed: the response failed" + (f"; {words}" if words else ""), None, words)
            failure.code = self._code(document["error"])
            failure.route = route_failure(self._model, purpose, None, failure.code, words)
            raise failure
        status = document.get("status")
        if status not in (None, "completed"):
            details = document.get("incomplete_details")
            reason = details.get("reason") if status == "incomplete" and isinstance(details, dict) else None
            known = isinstance(status, str) and status in STATUSES
            raise self._error(f"Foundry {purpose} failed: the response is {status if known else 'in a state that this app does not know'}"
                              + (f" ({reason})" if reason in ("max_output_tokens", "content_filter") else ""))
        output = document.get("output")
        if not isinstance(output, list) or not all(isinstance(item, dict) and isinstance(item.get("type"), str) for item in output):
            raise self._error(f"Foundry {purpose} failed: the answer holds no list of output items")
        return output

    def _calls(self, output: list[dict], purpose: str) -> list[dict]:
        """The function calls of the output items. Reasoning and messages are expected beside them, any other kind of item is not."""
        calls, ids = [], set()
        for item in output:
            kind = item["type"]
            if kind == "function_call":
                call_id, name, arguments = item.get("call_id"), item.get("name"), item.get("arguments")
                if (not isinstance(call_id, str) or not 1 <= len(call_id) <= 64 or call_id in ids or not isinstance(name, str) or not 1 <= len(name) <= 128
                        or not isinstance(arguments, str)):
                    raise self._error(f"Foundry {purpose} failed: a function call of the answer is not valid")
                ids.add(call_id)
                calls.append(item)
            elif kind not in ("message", "output_message", "reasoning"):
                raise self._error(f"Foundry {purpose} failed: the answer holds an item of a kind that this app does not use" + (f" ({kind})" if KIND.fullmatch(kind) else ""))
        return calls

    def _text(self, output: list[dict], purpose: str) -> str:
        parts = []
        for item in output:
            if item["type"] not in ("message", "output_message"):
                continue
            content = item.get("content")
            if item.get("role", "assistant") != "assistant" or not isinstance(content, list):
                raise self._error(f"Foundry {purpose} failed: a message of the answer is not one of the agent")
            for part in content:
                kind = part.get("type") if isinstance(part, dict) else None
                if kind == "output_text" and isinstance(part.get("text"), str):
                    parts.append(part["text"])
                elif kind == "refusal":
                    raise self._error(f"Foundry {purpose} failed: the agent refused to answer")
                else:
                    raise self._error(f"Foundry {purpose} failed: a message of the answer holds content that this app does not use")
        text = "\n".join(parts)
        if not text.strip():
            raise self._error(f"Foundry {purpose} failed: {NO_TEXT}")
        return text

    def _answer(self, call: dict, handler: ToolHandler, result: AgentRun) -> dict:
        """Runs one function call of the agent and returns the input item that answers it."""
        from .toolbox import MAX_RESULT_CHARS  # imported here: the toolbox imports this module, so a top-level import would be circular

        name = call["name"]
        try:
            parsed = json.loads(call["arguments"])
        except (ValueError, RecursionError):
            parsed = None
        entry: dict = {"name": name, "arguments": {}, "ok": False, "chars": 0}
        if isinstance(parsed, dict):
            entry["arguments"] = json.loads(call["arguments"])  # a second copy, so that the handler cannot change the record
            try:
                output = handler(name, parsed)
            except Exception:  # noqa: BLE001 (a tool that fails costs one answer, not the run)
                output = None
            entry["ok"] = isinstance(output, str)
            if not entry["ok"]:
                output = TOOL_FAILED
        else:
            output = BAD_ARGUMENTS
        if len(output) > MAX_RESULT_CHARS:
            output = output[: MAX_RESULT_CHARS - len(CUT_NOTE)] + CUT_NOTE
            entry["cut"] = True
        entry["chars"] = len(output)
        result.calls.append(entry)
        return {"type": "function_call_output", "call_id": call["call_id"], "output": output}

    @staticmethod
    def _refuse(call: dict, result: AgentRun) -> dict:
        """Answers a function call without running it, because the budget of tool calls is used up, and records it."""
        try:
            arguments = json.loads(call["arguments"])
        except (ValueError, RecursionError):
            arguments = None
        result.calls.append({"name": call["name"], "arguments": arguments if isinstance(arguments, dict) else {}, "ok": False, "chars": len(BUDGET_USED_UP),
                             "refused": True})
        return {"type": "function_call_output", "call_id": call["call_id"], "output": BUDGET_USED_UP}
