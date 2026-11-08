"""Tests of the Foundry client: the calls that it makes, the answers that it accepts, the errors that it gives and what it never puts in them.

No network and no Azure: a fake service stands in for the Foundry Agent Service and answers in the shapes of its REST reference (api-version v1).
"""
import dataclasses
import hashlib
import inspect
import json
import re
import socket
import traceback
import unittest
import urllib.error
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from support import LogCapture
from cases import foundry as fo
from cases import http
from cases.foundry import AgentRun, AgentSpec, Foundry, FoundryError, FunctionTool
from cases.http import Client
from cases.identity import IdentityError
from cases.redact import Redactor

HOST = "acct-example.services.ai.azure.com"
PROJECT = "/api/projects/proj-example"
ENDPOINT = f"https://{HOST}{PROJECT}"
NAME = "meternaut-investigator"
AGENT = f"{NAME}:3"
# Not shaped like a token, so that only registering it lets the redactor find it.
TOKEN = "tok-4f9a1c7e22b84d6f9d3a5b0c8e7f1a23c5d6e7f8"
# Shaped like a token of Microsoft Entra, so that the redactor finds it by its shape.
JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0LXVzZXIifQ.c2lnbmF0dXJlLXZhbHVlLWhlcmU"
PASS = object()  # in a list of failures: "now answer as the service does"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Service:
    """Foundry, as far as the client uses it. It keeps what was made, records every call, and answers like the REST reference says.

    `replies` is what the next POSTs of /responses answer: a document, (status, document or bytes), or a function of the request body that gives either.
    `failures` maps a route ("GET agent", "POST agents", "POST versions", "POST conversations", "POST responses", "DELETE conversation") to (status, document or bytes),
    (status, headers, document or bytes) or an exception, answered instead of the service's own answer; a list is used one item at a time (the last one stays), and PASS
    in it means the service's own answer. `accepts` is the one key of the agent reference that a response may carry ("agent" or "agent_reference"): a response with the other
    key is refused with an HTTP 400 whose error object is `refusal` (its texts take the refused key as {key}), before a reply is used."""

    def __init__(self, clock=None):
        self.clock, self.advance, self.client = clock, 0.0, None
        self.calls, self.responses = [], []
        self.agents, self.conversations = {}, {}
        self.replies, self.failures = [], {}
        self.accepts, self.refusal = None, {"code": "unknown_parameter", "message": "Unknown parameter: '{key}'."}

    @staticmethod
    def route(method, path):
        if path == "/agents":
            return f"{method} agents"
        if re.fullmatch(r"/agents/[^/]+", path):
            return f"{method} agent"
        if re.fullmatch(r"/agents/[^/]+/versions", path):
            return f"{method} versions"
        if path == "/openai/v1/conversations":
            return f"{method} conversations"
        if re.fullmatch(r"/openai/v1/conversations/[^/]+", path):
            return f"{method} conversation"
        if path == "/openai/v1/responses":
            return f"{method} responses"
        return f"{method} {path}"

    @staticmethod
    def answer(planned):
        status, headers, document = planned if len(planned) == 3 else (planned[0], {}, planned[1])
        return status, headers, document if isinstance(document, bytes) else json.dumps(document).encode("utf-8")

    def __call__(self, method, url, headers, data, timeout):
        parts = urlsplit(url)
        path = parts.path.removeprefix(PROJECT)
        body = json.loads(data.decode("utf-8")) if data else None
        route = self.route(method, path)
        self.calls.append({"method": method, "host": parts.netloc, "path": path, "query": parse_qs(parts.query), "headers": dict(headers), "body": body, "timeout": timeout,
                           "route": route, "deadline": None if self.client is None else self.client.deadline})
        if self.clock is not None:
            self.clock.now += self.advance
        planned = self.failures.get(route)
        if isinstance(planned, list):
            planned = planned.pop(0) if len(planned) > 1 else planned[0]
        if isinstance(planned, Exception):
            raise planned
        if planned is not None and planned is not PASS:
            return self.answer(planned)
        return self.own(route, path, body)

    def own(self, route, path, body):
        name = path.split("/")[2] if path.startswith("/agents/") else None
        if route == "GET agent":
            return self.answer((200, self.agent(name))) if name in self.agents else self.answer((404, {"error": {"code": "not_found", "message": "Agent not found"}}))
        if route == "POST agents":
            if body["name"] in self.agents:
                return self.answer((409, {"error": {"code": "conflict", "message": "The agent exists"}}))
            self.agents[body["name"]] = [self.version(body["name"], body, 1)]
            return self.answer((200, self.agent(body["name"])))
        if route == "POST versions":
            if name not in self.agents:
                return self.answer((404, {"error": {"code": "not_found", "message": "Agent not found"}}))
            self.agents[name].append(self.version(name, body, len(self.agents[name]) + 1))
            return self.answer((200, self.agents[name][-1]))
        if route == "POST conversations":
            identifier = f"conv_{len(self.conversations) + 1:04d}abc"
            self.conversations[identifier] = body["items"]
            return self.answer((200, {"id": identifier, "object": "conversation", "created_at": 1, "metadata": {}}))
        if route == "POST responses":
            self.responses.append(body)
            if self.accepts is not None and self.accepts not in body:
                sent = next((key for key in ("agent_reference", "agent") if key in body), "none")
                return self.answer((400, {"error": {k: v.format(key=sent) for k, v in self.refusal.items()}}))
            reply = self.replies.pop(0)
            reply = reply(body) if callable(reply) else reply
            return self.answer(reply) if isinstance(reply, tuple) else self.answer((200, reply))
        if route == "DELETE conversation":
            identifier = path.rsplit("/", 1)[1]
            if identifier in self.conversations:
                del self.conversations[identifier]
                return self.answer((200, {"id": identifier, "object": "conversation.deleted", "deleted": True}))
            return self.answer((404, {"error": {"code": "not_found", "message": "Conversation not found"}}))
        return self.answer((404, {"error": {"code": "no_route", "message": route}}))

    @staticmethod
    def version(name, body, number):
        return {"object": "agent.version", "id": f"{name}:{number}", "name": name, "version": str(number), "description": body.get("description"), "created_at": 1,
                "metadata": body.get("metadata"), "definition": body["definition"]}

    def agent(self, name):
        return {"object": "agent", "id": name, "name": name, "versions": {"latest": self.agents[name][-1]}}

    def routes(self):
        return [call["route"] for call in self.calls]


class Lookup:
    """socket.getaddrinfo, answered from a list of addresses (or by an error), and counted."""

    def __init__(self, *addresses, error=None):
        self.addresses, self.error, self.calls = addresses, error, []

    def __call__(self, host, port, **options):
        self.calls.append((host, port, options))
        if self.error is not None:
            raise self.error
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (a, port, 0, 0)) if ":" in a else (socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port)) for a in self.addresses]


class Rig:
    """A client of the list of calls, with a fake service, a clock that the service may move, a lookup of host names and a token that is asked for."""

    def __init__(self, *, token=TOKEN, lookup=None, allowed=None, redact=None):
        self.clock, self.token, self.resources, self.sleeps = Clock(), token, [], []
        self.service = Service(self.clock)
        self.redact = redact or Redactor()
        calls = allowed if allowed is not None else http.allowed_calls(ENDPOINT)
        self.client = Client(calls, self.redact, transport=self.service, sleep=self.sleeps.append, jitter=lambda: 0.5, monotonic=self.clock)
        self.service.client = self.client
        self.lookup = lookup or Lookup("10.1.2.3")
        self.foundry = Foundry(ENDPOINT, self.client, self.issue, self.redact)
        self.foundry.resolve = self.lookup

    def issue(self, resource):
        self.resources.append(resource)
        if isinstance(self.token, Exception):
            raise self.token
        return self.token

    def run(self, *replies, handler=None, **options):
        self.service.replies = list(replies)
        return self.foundry.run(AGENT, "Look at the estate.", handler, **options)


class Handler:
    """A tool handler: it answers from a list (the last answer stays), raises an answer that is an exception, and records what it was asked."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers) or ['{"ok":true}'], []

    def __call__(self, name, arguments):
        self.calls.append((name, arguments))
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, BaseException):
            raise answer
        return answer


def spec(**changes):
    values = dict(name=NAME, description="Finds waste.", model="gpt-6.1-sol", instructions="You find waste.",
                  tools=(FunctionTool("inspect_resource", "Shows one resource.", {"type": "object", "properties": {"handle": {"type": "string"}}, "required": ["handle"]}),))
    values.update(changes)
    return AgentSpec(**values)


def usage(input_tokens=10, output_tokens=5):
    return {"input_tokens": input_tokens, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": output_tokens, "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": input_tokens + output_tokens}


def reply(output, input_tokens=10, output_tokens=5, **extra):
    return {"id": "resp_1", "object": "response", "status": "completed", "error": None, "output": output, "usage": usage(input_tokens, output_tokens), **extra}


def call(name, arguments, call_id="call_1"):
    return {"type": "function_call", "id": f"fc_{call_id}", "call_id": call_id, "name": name,
            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments), "status": "completed"}


def message(text):
    return {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": text, "annotations": []}]}


def reasoning():
    return {"type": "reasoning", "id": "rs_1", "summary": []}


def output_of(call_id, output):
    return {"type": "function_call_output", "call_id": call_id, "output": output}


class Interface(unittest.TestCase):
    """The interface that the investigation is written against."""

    def test_the_signatures_and_the_dataclasses_are_the_ones_that_were_fixed(self):
        init = inspect.signature(Foundry.__init__).parameters
        self.assertEqual([(p.name, p.kind.name) for p in init.values()], [("self", "POSITIONAL_OR_KEYWORD"), ("endpoint", "POSITIONAL_OR_KEYWORD"), ("client", "POSITIONAL_OR_KEYWORD"),
                                                                           ("token", "POSITIONAL_OR_KEYWORD"), ("redact", "POSITIONAL_OR_KEYWORD")])
        ensure = inspect.signature(Foundry.ensure_agent).parameters
        self.assertEqual([p.name for p in ensure.values()], ["self", "spec"])
        run = inspect.signature(Foundry.run).parameters
        self.assertEqual([(p.name, p.kind.name, p.default) for p in run.values()],
                         [("self", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty), ("agent", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty),
                          ("user_input", "POSITIONAL_OR_KEYWORD", inspect.Parameter.empty), ("handler", "POSITIONAL_OR_KEYWORD", None),
                          ("max_calls", "KEYWORD_ONLY", 20), ("max_seconds", "KEYWORD_ONLY", None)])
        self.assertEqual([f.name for f in dataclasses.fields(FunctionTool)], ["name", "description", "parameters"])
        self.assertEqual([f.name for f in dataclasses.fields(AgentSpec)], ["name", "description", "model", "instructions", "tools", "reasoning_effort"])
        self.assertIsNone(AgentSpec("n", "d", "m", "i").reasoning_effort, "the effort is left out unless a spec asks for one")
        self.assertEqual([f.name for f in dataclasses.fields(AgentRun)], ["text", "calls", "input_tokens", "output_tokens", "responses", "out_of_time"])
        for frozen, cls in ((True, FunctionTool), (True, AgentSpec), (False, AgentRun)):
            self.assertEqual(cls.__dataclass_params__.frozen, frozen, cls.__name__)

    def test_an_error_of_the_client_is_an_exception_that_says_nothing_until_it_is_given_a_status_or_a_partial_run(self):
        error = FoundryError("x")
        self.assertEqual((str(error), error.status, error.partial), ("x", None, None))


class Endpoint(unittest.TestCase):
    @staticmethod
    def make(endpoint):
        return Foundry(endpoint, Client((), Redactor()), lambda resource: TOKEN, Redactor())

    def test_the_endpoint_of_a_project_is_accepted_with_or_without_one_slash_at_the_end(self):
        for given in (ENDPOINT, ENDPOINT + "/", "https://a1.services.ai.azure.com/api/projects/_project", "https://ab.services.ai.azure.com/api/projects/P_1-x"):
            expected = given.removesuffix("/")
            foundry = self.make(given)
            self.assertEqual((foundry.endpoint, foundry.host), (expected, urlsplit(expected).netloc), given)

    def test_a_project_name_may_hold_dots_after_its_first_character_as_the_name_of_a_resource_does(self):
        for name in ("proj.v2", "a.b.c-d_e", "p.", "a.", "P.1", "p" * 31 + "." + "q" * 32):
            with self.subTest(name=name):
                given = f"https://ab.services.ai.azure.com/api/projects/{name}"
                foundry = self.make(given)
                self.assertEqual((foundry.endpoint, foundry.host), (given, "ab.services.ai.azure.com"))
                self.assertEqual(self.make(given + "/").endpoint, given)

    def test_a_name_that_is_a_dot_or_starts_with_one_or_is_too_long_is_refused_so_that_it_can_never_be_a_step_up_in_the_path(self):
        account = "acct-example.services.ai.azure.com"
        for name in (".", "..", "...", ".p", "..p", ".p.", "p/.", "p/..", "p%2e", "p%2E%2E", "p" * 32 + "." + "q" * 32, "p..q/../r"):
            with self.subTest(name=name):
                with self.assertRaises(FoundryError):
                    self.make(f"https://{account}/api/projects/{name}")

    def test_anything_else_is_refused_and_the_text_does_not_repeat_it(self):
        account = "acct-example.services.ai.azure.com"
        for given in ("", "x", None, 5, f"http://{account}/api/projects/p", f"https://{account}/api/projects/", f"https://{account}/api/projects/p/agents",
                      f"https://{account}/api/projects/p?x=1", f"https://{account}", f"https://{account}/api/projects/p//", f"https://{account}/api/projects/p\n",
                      f"https://{account}/api/projects/p q", f"https://{account}:443/api/projects/p", f"https://user@{account}/api/projects/p",
                      f"https://{account.upper()}/api/projects/p", "https://acct-example.openai.azure.com/api/projects/p", "https://-a.services.ai.azure.com/api/projects/p",
                      "https://acct-example-services-ai-azure-com/api/projects/p",
                      f"https://{account}.evil.example/api/projects/p", f"https://evil.example/https://{account}/api/projects/p", f"https://{account}/api/projects/{'p' * 65}"):
            with self.assertRaises(FoundryError, msg=repr(given)) as raised:
                self.make(given)
            self.assertIn("https://<account>.services.ai.azure.com/api/projects/<project>", str(raised.exception))
            self.assertNotIn("acct-example", str(raised.exception))

    def test_a_client_that_looks_hosts_up_with_the_standard_library_until_a_test_says_otherwise(self):
        self.assertIs(self.make(ENDPOINT).resolve, socket.getaddrinfo)


class EnsureAgent(unittest.TestCase):
    def test_an_agent_that_is_not_there_is_made_with_its_definition_and_the_hash_of_it(self):
        rig = Rig()
        self.assertEqual(rig.foundry.ensure_agent(spec()), f"{NAME}:1")
        get, post = rig.service.calls
        self.assertEqual((get["method"], get["path"], get["query"], get["body"]), ("GET", f"/agents/{NAME}", {"api-version": ["v1"]}, None))
        self.assertEqual((post["method"], post["path"], post["query"]), ("POST", "/agents", {"api-version": ["v1"]}))
        body = post["body"]
        self.assertEqual(set(body), {"name", "description", "definition", "metadata"})
        self.assertEqual((body["name"], body["description"]), (NAME, "Finds waste."))
        self.assertEqual(body["definition"], {
            "kind": "prompt", "model": "gpt-6.1-sol", "instructions": "You find waste.",
            "tools": [{"type": "function", "name": "inspect_resource", "description": "Shows one resource.", "strict": False,
                       "parameters": {"type": "object", "properties": {"handle": {"type": "string"}}, "required": ["handle"]}}]})
        self.assertEqual(list(body["metadata"]), [fo.HASH_KEY])
        self.assertRegex(body["metadata"][fo.HASH_KEY], r"^[0-9a-f]{64}$")
        for each in (get, post):
            self.assertEqual(each["headers"]["Authorization"], f"Bearer {TOKEN}")
            self.assertEqual(each["host"], HOST)
        self.assertEqual(post["headers"]["Content-Type"], "application/json")
        self.assertEqual(set(rig.resources), {"https://ai.azure.com"}, "the token is for the resource of Foundry")

    def test_an_agent_that_did_not_change_costs_one_read_and_no_version(self):
        rig = Rig()
        rig.foundry.ensure_agent(spec())
        rig.service.calls.clear()
        self.assertEqual(rig.foundry.ensure_agent(spec()), f"{NAME}:1")
        self.assertEqual(rig.service.routes(), ["GET agent"])
        self.assertEqual(len(rig.service.agents[NAME]), 1)

    def test_a_changed_definition_makes_a_new_version_with_its_own_hash_and_then_costs_one_read(self):
        other_tool = FunctionTool("inspect_resource", "Shows one resource.", {"type": "object", "properties": {"handle": {"type": "string"}}, "required": ["handle"]})
        changes = {
            "model": {"model": "gpt-6-luna"}, "instructions": {"instructions": "You find more."}, "description": {"description": "Other."}, "no description": {"description": ""},
            "no tools": {"tools": ()},
            "tool description": {"tools": (FunctionTool(other_tool.name, "Shows two.", other_tool.parameters),)},
            "tool schema": {"tools": (FunctionTool(other_tool.name, other_tool.description, {"type": "object", "properties": {}}),)},
            "tool name": {"tools": (FunctionTool("show_resource", other_tool.description, other_tool.parameters),)},
            "one more tool": {"tools": (other_tool, FunctionTool("list_things", "Lists.", {"type": "object", "properties": {}}))},
            "a reasoning effort": {"reasoning_effort": "none"},
        }
        for what, change in changes.items():
            with self.subTest(what):
                rig = Rig()
                rig.foundry.ensure_agent(spec())
                first = rig.service.agents[NAME][0]["metadata"][fo.HASH_KEY]
                rig.service.calls.clear()
                self.assertEqual(rig.foundry.ensure_agent(spec(**change)), f"{NAME}:2")
                self.assertEqual(rig.service.routes(), ["GET agent", "POST versions"])
                post = rig.service.calls[1]
                self.assertEqual((post["path"], post["query"]), (f"/agents/{NAME}/versions", {"api-version": ["v1"]}))
                self.assertNotIn("name", post["body"], "the name is in the address of a new version")
                self.assertNotEqual(post["body"]["metadata"][fo.HASH_KEY], first)
                rig.service.calls.clear()
                self.assertEqual(rig.foundry.ensure_agent(spec(**change)), f"{NAME}:2")
                self.assertEqual(rig.service.routes(), ["GET agent"])

    def test_the_definition_that_the_service_stores_is_not_compared_only_the_hash_of_the_definition_is(self):
        rig = Rig()
        rig.foundry.ensure_agent(spec())
        rig.service.agents[NAME][-1]["definition"] = {"kind": "prompt", "model": "gpt-6.1-sol", "temperature": 1, "top_p": 1, "tools": [{"strict": False}]}
        rig.service.calls.clear()
        self.assertEqual(rig.foundry.ensure_agent(spec()), f"{NAME}:1")
        self.assertEqual(rig.service.routes(), ["GET agent"])

    def test_a_version_without_the_hash_is_replaced_by_a_new_version(self):
        for kept in (None, {}, {"other": "x"}, {fo.HASH_KEY: "0" * 64}, {fo.HASH_KEY: None}, "text", ["x"]):
            with self.subTest(kept=kept):
                rig = Rig()
                rig.foundry.ensure_agent(spec())
                rig.service.agents[NAME][-1]["metadata"] = kept
                self.assertEqual(rig.foundry.ensure_agent(spec()), f"{NAME}:2")

    def test_the_hash_is_the_same_whatever_the_order_of_the_keys_of_a_schema(self):
        one = spec(tools=(FunctionTool("t", "d", {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "integer"}}}),))
        two = spec(tools=(FunctionTool("t", "d", {"properties": {"b": {"type": "integer"}, "a": {"type": "string"}}, "type": "object"}),))
        rig = Rig()
        rig.foundry.ensure_agent(one)
        rig.service.calls.clear()
        self.assertEqual(rig.foundry.ensure_agent(two), f"{NAME}:1")
        self.assertEqual(rig.service.routes(), ["GET agent"])

    def test_the_hash_is_the_sha256_of_the_definition_as_sorted_compact_json_and_is_pinned(self):
        # A change of what is sent changes this hash, and that makes a new version of every agent in every project: do it on purpose.
        rig = Rig()
        rig.foundry.ensure_agent(spec(tools=(), description=""))
        expected = hashlib.sha256(b'{"definition":{"instructions":"You find waste.","kind":"prompt","model":"gpt-6.1-sol"}}').hexdigest()
        self.assertEqual(rig.service.agents[NAME][0]["metadata"][fo.HASH_KEY], expected)
        rig = Rig()
        rig.foundry.ensure_agent(spec(tools=(FunctionTool("t", "d", {"type": "object"}),)))
        expected = hashlib.sha256(b'{"definition":{"instructions":"You find waste.","kind":"prompt","model":"gpt-6.1-sol","tools":[{"description":"d","name":"t",'
                                  b'"parameters":{"type":"object"},"strict":false,"type":"function"}]},"description":"Finds waste."}').hexdigest()
        self.assertEqual(rig.service.agents[NAME][0]["metadata"][fo.HASH_KEY], expected)
        rig = Rig()
        rig.foundry.ensure_agent(spec(tools=(), description="", reasoning_effort="none"))
        expected = hashlib.sha256(b'{"definition":{"instructions":"You find waste.","kind":"prompt","model":"gpt-6.1-sol","reasoning":{"effort":"none"}}}').hexdigest()
        self.assertEqual(rig.service.agents[NAME][0]["metadata"][fo.HASH_KEY], expected, "an agent that has an effort is another version than one that has none")

    def test_a_reasoning_effort_is_sent_as_reasoning_effort_of_the_definition_and_only_when_the_spec_has_one(self):
        rig = Rig()
        rig.foundry.ensure_agent(spec(reasoning_effort="none"))
        definition = rig.service.calls[1]["body"]["definition"]
        self.assertEqual(definition["reasoning"], {"effort": "none"})
        self.assertEqual(set(definition), {"kind", "model", "instructions", "tools", "reasoning"})
        rig = Rig()
        rig.foundry.ensure_agent(spec())
        self.assertNotIn("reasoning", rig.service.calls[1]["body"]["definition"], "the default is that the effort is not sent")

    def test_an_agent_that_had_no_effort_gets_a_new_version_when_a_spec_asks_for_one_and_costs_one_read_after_that(self):
        rig = Rig()
        self.assertEqual(rig.foundry.ensure_agent(spec()), f"{NAME}:1")
        rig.service.calls.clear()
        self.assertEqual(rig.foundry.ensure_agent(spec(reasoning_effort="none")), f"{NAME}:2")
        self.assertEqual(rig.service.routes(), ["GET agent", "POST versions"])
        self.assertEqual(rig.service.calls[1]["body"]["definition"]["reasoning"], {"effort": "none"})
        rig.service.calls.clear()
        self.assertEqual(rig.foundry.ensure_agent(spec(reasoning_effort="none")), f"{NAME}:2")
        self.assertEqual(rig.service.routes(), ["GET agent"])

    def test_no_tools_and_no_description_are_left_out_of_what_is_sent(self):
        rig = Rig()
        rig.foundry.ensure_agent(spec(tools=(), description=""))
        body = rig.service.calls[1]["body"]
        self.assertEqual(set(body), {"name", "definition", "metadata"})
        self.assertEqual(set(body["definition"]), {"kind", "model", "instructions"})

    def test_a_spec_that_cannot_be_sent_is_refused_before_any_call(self):
        tool = FunctionTool("t", "d", {})
        bad = {
            "a name with a slash": spec(name="a/b"), "an empty name": spec(name=""), "a name of 64 characters": spec(name="a" * 64), "a name that ends with a hyphen": spec(name="abc-"),
            "a name that starts with a hyphen": spec(name="-abc"), "a name with a query": spec(name="a?b"), "a name of dots": spec(name=".."), "a name that is not text": spec(name=5),
            "no model": spec(model=" "), "a model that is not text": spec(model=None), "instructions that are not text": spec(instructions=None),
            "a description of 513 characters": spec(description="x" * 513), "a description that is not text": spec(description=None), "tools that are not a tuple": spec(tools="x"),
            "129 tools": spec(tools=tuple(FunctionTool(f"t{i}", "d", {}) for i in range(129))), "a tool that is not a tool": spec(tools=("x",)),
            "a tool name with a space": spec(tools=(FunctionTool("a b", "d", {}),)), "an empty tool name": spec(tools=(FunctionTool("", "d", {}),)),
            "a tool name of 65 characters": spec(tools=(FunctionTool("a" * 65, "d", {}),)), "a tool name that is not text": spec(tools=(FunctionTool(5, "d", {}),)),
            "the same tool twice": spec(tools=(tool, tool)), "a tool description that is not text": spec(tools=(FunctionTool("t", None, {}),)),
            "parameters that are not an object": spec(tools=(FunctionTool("t", "d", "x"),)),
            "a schema that cannot be JSON": spec(tools=(FunctionTool("t", "d", {"x": object()}),)), "a schema with NaN": spec(tools=(FunctionTool("t", "d", {"x": float("nan")}),)),
            "an empty effort": spec(reasoning_effort=""), "an effort in capitals": spec(reasoning_effort="None"), "an effort that is not text": spec(reasoning_effort=5),
            "an effort of two words": spec(reasoning_effort="very high"), "an effort that is True": spec(reasoning_effort=True), "an effort of 17 letters": spec(reasoning_effort="a" * 17),
        }
        for what, each in bad.items():
            with self.subTest(what):
                rig = Rig()
                with self.assertRaises(FoundryError):
                    rig.foundry.ensure_agent(each)
                self.assertEqual(rig.service.calls, [])

    def test_the_edges_of_what_is_allowed_are_allowed(self):
        rig = Rig()
        rig.foundry.ensure_agent(spec(name="a" * 63, description="x" * 512, tools=tuple(FunctionTool(f"t{i}", "d", {}) for i in range(128))))
        rig = Rig()
        rig.foundry.ensure_agent(spec(name="a", tools=(FunctionTool("a" * 64, "d", {}), FunctionTool("A_b-9", "d", {}))))
        for effort in ("none", "minimal", "low", "medium", "high", "xhigh", "max"):
            with self.subTest(effort=effort):
                rig = Rig()
                rig.foundry.ensure_agent(spec(reasoning_effort=effort))
                self.assertEqual(rig.service.calls[1]["body"]["definition"]["reasoning"], {"effort": effort})

    def test_an_answer_that_is_not_an_agent_is_an_error_and_is_not_acted_on(self):
        shapes = {"no versions": {"name": NAME}, "versions that are not an object": {"versions": []}, "no latest": {"versions": {}}, "latest that is not an object": {"versions": {"latest": 1}},
                  "another name": {"versions": {"latest": {"name": "other", "version": "2"}}}, "no version": {"versions": {"latest": {"name": NAME}}},
                  "an empty version": {"versions": {"latest": {"name": NAME, "version": ""}}}, "a version with a space": {"versions": {"latest": {"name": NAME, "version": "a b"}}},
                  "a version that is a flag": {"versions": {"latest": {"name": NAME, "version": True}}}, "a version that is a fraction": {"versions": {"latest": {"name": NAME, "version": 2.5}}},
                  "a version with a slash": {"versions": {"latest": {"name": NAME, "version": "1/2"}}}}
        for what, shape in shapes.items():
            with self.subTest(what):
                rig = Rig()
                rig.service.failures["GET agent"] = (200, shape)
                with self.assertRaises(FoundryError) as raised:
                    rig.foundry.ensure_agent(spec())
                self.assertIn("Foundry read agent failed", str(raised.exception))
                self.assertEqual(rig.service.routes(), ["GET agent"])
        rig = Rig()
        rig.foundry.ensure_agent(spec())
        stored = rig.service.agents[NAME][0]
        rig.service.failures["GET agent"] = (200, {"name": NAME, "versions": {"latest": {**stored, "version": "3"}}})
        self.assertEqual(rig.foundry.ensure_agent(spec()), f"{NAME}:3", "an answer that is well formed is read")
        for what, answer in (("a list", []), ("text", "x"), ("nothing", b""), ("no JSON", b"<html>")):
            with self.subTest(what):
                rig = Rig()
                rig.service.failures["GET agent"] = (200, answer)
                with self.assertRaises(FoundryError):
                    rig.foundry.ensure_agent(spec())

    def test_the_answers_to_a_creation_are_checked_like_the_answer_to_a_read(self):
        for route, setup in (("POST agents", lambda rig: None), ("POST versions", lambda rig: rig.foundry.ensure_agent(spec(model="gpt-6-luna")))):
            for what, shape in (("no version", {"name": NAME}), ("another name", {"name": "other", "version": "1", "versions": {"latest": {"name": "other", "version": "1"}}}),
                                ("no latest", {"object": "agent", "name": NAME})):
                with self.subTest(route=route, what=what):
                    rig = Rig()
                    setup(rig)
                    rig.service.failures[route] = (200, shape)
                    with self.assertRaises(FoundryError):
                        rig.foundry.ensure_agent(spec())

    def test_a_version_that_the_service_numbers_with_an_integer_is_read_as_text(self):
        rig = Rig()
        rig.service.failures["POST agents"] = (200, {"name": NAME, "versions": {"latest": {"name": NAME, "version": 7}}})
        self.assertEqual(rig.foundry.ensure_agent(spec()), f"{NAME}:7")

    def test_a_new_version_answers_with_its_own_version_object_and_an_agent_answers_with_the_latest(self):
        rig = Rig()
        rig.service.failures["POST agents"] = (200, {"name": NAME, "versions": {"latest": {"name": NAME, "version": "4"}}})
        self.assertEqual(rig.foundry.ensure_agent(spec()), f"{NAME}:4")
        rig = Rig()
        rig.foundry.ensure_agent(spec())
        rig.service.failures["POST versions"] = (200, {"name": NAME, "version": "9", "id": "x"})
        self.assertEqual(rig.foundry.ensure_agent(spec(model="gpt-6-luna")), f"{NAME}:9")

    def test_what_is_logged_is_the_name_and_the_version_and_never_the_definition(self):
        rig = Rig()
        with LogCapture() as logs:
            rig.foundry.ensure_agent(spec())
            rig.foundry.ensure_agent(spec(model="gpt-6-luna"))
            rig.foundry.ensure_agent(spec(model="gpt-6-luna"))
        self.assertEqual([m for m in logs.messages() if m.startswith("Foundry agent")], [f"Foundry agent {NAME}: made, version 1", f"Foundry agent {NAME}: new version 2"])
        self.assertNotIn("You find waste", " ".join(logs.messages()))


class Run(unittest.TestCase):
    def test_a_run_without_tools_makes_a_conversation_asks_once_gives_the_text_and_deletes_the_conversation(self):
        rig = Rig()
        result = rig.run(reply([message("All good.")], 120, 30))
        self.assertEqual((result.text, result.calls, result.input_tokens, result.output_tokens, result.responses), ("All good.", [], 120, 30, 1))
        self.assertEqual([(c["method"], c["path"]) for c in rig.service.calls],
                         [("POST", "/openai/v1/conversations"), ("POST", "/openai/v1/responses"), ("DELETE", "/openai/v1/conversations/conv_0001abc")])
        conversation, response, delete = rig.service.calls
        self.assertEqual(conversation["body"], {"items": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Look at the estate."}]}]})
        self.assertEqual(response["body"], {"agent_reference": {"type": "agent_reference", "name": NAME, "version": "3"}, "conversation": "conv_0001abc", "input": []})
        self.assertEqual([c["query"] for c in rig.service.calls], [{}, {}, {}], "the /openai/v1 calls carry no api-version")
        for each in rig.service.calls:
            self.assertEqual((each["host"], each["headers"]["Authorization"]), (HOST, f"Bearer {TOKEN}"))
        self.assertIsNone(delete["body"])
        self.assertEqual(rig.service.conversations, {})
        self.assertEqual(set(rig.resources), {"https://ai.azure.com"})
        self.assertIs(rig.client.transport, rig.service, "the transport of the client is put back")

    def test_a_run_by_name_does_not_pin_a_version(self):
        rig = Rig()
        rig.service.replies = [reply([message("ok")])]
        rig.foundry.run(NAME, "Go.")
        self.assertEqual(rig.service.responses[0]["agent_reference"], {"type": "agent_reference", "name": NAME})

    def test_an_agent_that_is_not_a_name_or_a_name_and_a_version_is_refused_before_any_call(self):
        for agent in ("", "a/b", "a:", ":1", "a:b c", "a:1:2", "a" * 64, "-a", None, 5, "a:" + "1" * 65):
            with self.subTest(agent=agent):
                rig = Rig()
                with self.assertRaises(FoundryError):
                    rig.foundry.run(agent, "Go.")
                self.assertEqual(rig.service.calls, [])

    def test_the_other_arguments_are_checked_before_any_call(self):
        for what, arguments in (("no input", dict(user_input="")), ("blank input", dict(user_input=" \n")), ("input that is not text", dict(user_input=None)),
                                ("negative calls", dict(max_calls=-1)), ("calls that are a fraction", dict(max_calls=1.5)), ("calls that are a flag", dict(max_calls=True)),
                                ("no seconds", dict(max_seconds=0)), ("negative seconds", dict(max_seconds=-5)), ("seconds that are text", dict(max_seconds="9")),
                                ("seconds that are a flag", dict(max_seconds=True)), ("seconds that are not a number", dict(max_seconds=float("nan")))):
            with self.subTest(what):
                rig = Rig()
                options = {"user_input": "Go.", **arguments}
                with self.assertRaises(FoundryError):
                    rig.foundry.run(AGENT, options.pop("user_input"), None, **options)
                self.assertEqual(rig.service.calls, [])
                self.assertIsNone(rig.client.deadline)

    def test_two_tools_one_after_the_other_and_each_answer_goes_back_in_the_same_conversation(self):
        rig = Rig()
        handler = Handler('{"cost":12.5}', '{"cost":0}')
        result = rig.run(reply([reasoning(), call("inspect_resource", {"handle": "r1"}, "call_a")], 100, 10), reply([call("inspect_resource", {"handle": "r2"}, "call_b")], 150, 12),
                         reply([message('{"findings":[]}')], 200, 40), handler=handler)
        self.assertEqual(handler.calls, [("inspect_resource", {"handle": "r1"}), ("inspect_resource", {"handle": "r2"})])
        self.assertEqual([body["input"] for body in rig.service.responses],
                         [[], [output_of("call_a", '{"cost":12.5}')], [output_of("call_b", '{"cost":0}')]])
        self.assertEqual({body["conversation"] for body in rig.service.responses}, {"conv_0001abc"})
        self.assertEqual({json.dumps(body["agent_reference"]) for body in rig.service.responses}, {json.dumps({"type": "agent_reference", "name": NAME, "version": "3"})})
        self.assertEqual(result.text, '{"findings":[]}')
        self.assertEqual(result.calls, [{"name": "inspect_resource", "arguments": {"handle": "r1"}, "ok": True, "chars": len('{"cost":12.5}')},
                                        {"name": "inspect_resource", "arguments": {"handle": "r2"}, "ok": True, "chars": len('{"cost":0}')}])
        self.assertEqual((result.input_tokens, result.output_tokens, result.responses), (450, 62, 3))
        self.assertEqual(rig.service.routes()[-1], "DELETE conversation")

    def test_several_calls_in_one_answer_are_all_answered_in_one_input_list_in_order(self):
        rig = Rig()
        handler = Handler('{"n":1}', '{"n":2}', '{"n":3}')
        result = rig.run(reply([call("a", {}, "c1"), message("thinking aloud"), call("b", {"x": 1}, "c2"), call("c", "{}", "c3")]), reply([message("done")]), handler=handler)
        self.assertEqual(handler.calls, [("a", {}), ("b", {"x": 1}), ("c", {})])
        self.assertEqual(rig.service.responses[1]["input"], [output_of("c1", '{"n":1}'), output_of("c2", '{"n":2}'), output_of("c3", '{"n":3}')])
        self.assertEqual(len(rig.service.responses), 2, "one request for the three answers")
        self.assertEqual([c["name"] for c in result.calls], ["a", "b", "c"])
        self.assertEqual(result.text, "done")

    def test_a_handler_that_raises_gives_the_agent_a_fixed_error_and_the_run_goes_on(self):
        rig = Rig()
        handler = Handler(RuntimeError("SECRET-DETAIL of the failure"), '{"ok":1}')
        result = rig.run(reply([call("t", {"a": 1}, "c1")]), reply([call("t", {"a": 2}, "c2")]), reply([message("fine")]), handler=handler)
        self.assertEqual(rig.service.responses[1]["input"], [output_of("c1", '{"error":"tool-failed"}')])
        self.assertEqual(rig.service.responses[2]["input"], [output_of("c2", '{"ok":1}')])
        self.assertEqual([(c["ok"], c["chars"]) for c in result.calls], [(False, len('{"error":"tool-failed"}')), (True, 8)])
        self.assertEqual(result.text, "fine")
        self.assertNotIn("SECRET-DETAIL", json.dumps(rig.service.calls) + repr(result))

    def test_a_handler_that_gives_no_string_is_a_failed_tool_too(self):
        for answer in (None, {"cost": 1}, 5, b"bytes", ["x"]):
            with self.subTest(answer=answer):
                rig = Rig()
                result = rig.run(reply([call("t", {}, "c1")]), reply([message("fine")]), handler=Handler(answer))
                self.assertEqual(rig.service.responses[1]["input"], [output_of("c1", '{"error":"tool-failed"}')])
                self.assertEqual(result.calls[0]["ok"], False)

    def test_arguments_that_are_not_a_json_object_are_not_given_to_the_handler_and_the_agent_is_told(self):
        for arguments in ("", "not json", "[1, 2]", "5", '"text"', "null", "true", "{", '{"a":', "[" * 5000):
            with self.subTest(arguments=arguments[:20]):
                rig = Rig()
                handler = Handler('{"ok":1}')
                result = rig.run(reply([call("t", arguments, "c1")]), reply([message("fine")]), handler=handler)
                self.assertEqual(handler.calls, [])
                self.assertEqual(rig.service.responses[1]["input"], [output_of("c1", '{"error":"bad-arguments"}')])
                self.assertEqual(result.calls, [{"name": "t", "arguments": {}, "ok": False, "chars": len('{"error":"bad-arguments"}')}])

    def test_the_handler_gets_a_dict_and_the_record_keeps_its_own_copy(self):
        nested = {"a": {"b": [1, 2, {"c": None}]}, "handle": "r1"}
        rig = Rig()

        def meddling(name, arguments):
            self.assertEqual(arguments, nested)
            self.assertIsInstance(arguments, dict)
            arguments["handle"] = "changed"
            arguments["a"]["b"].append("changed")
            return "{}"

        result = rig.run(reply([call("t", nested, "c1")]), reply([message("fine")]), handler=meddling)
        self.assertEqual(result.calls[0]["arguments"], nested)

    def test_arguments_that_are_nested_deeper_than_a_copy_can_be_made_do_not_stop_the_run(self):
        deep = '{"a":' * 500 + "1" + "}" * 500
        rig = Rig()
        handler = Handler('{"ok":1}')
        result = rig.run(reply([call("t", deep, "c1")]), reply([message("fine")]), handler=handler)
        self.assertEqual((len(handler.calls), result.calls[0]["ok"], result.text), (1, True, "fine"))

    def test_a_result_longer_than_the_limit_is_cut_and_says_so(self):
        from cases.toolbox import MAX_RESULT_CHARS
        for length, cut in ((10, False), (MAX_RESULT_CHARS - 1, False), (MAX_RESULT_CHARS, False), (MAX_RESULT_CHARS + 1, True), (MAX_RESULT_CHARS * 5, True)):
            with self.subTest(length=length):
                rig = Rig()
                result = rig.run(reply([call("t", {}, "c1")]), reply([message("fine")]), handler=Handler("x" * length))
                (sent,) = [item["output"] for item in rig.service.responses[1]["input"]]
                self.assertLessEqual(len(sent), MAX_RESULT_CHARS)
                self.assertEqual(sent.endswith(fo.CUT_NOTE), cut)
                self.assertEqual(sent.startswith("x" * 100), length >= 100)
                self.assertEqual(result.calls[0].get("cut"), True if cut else None)
                self.assertEqual(result.calls[0]["chars"], len(sent))
                self.assertEqual(len(sent), MAX_RESULT_CHARS if cut else length)

    def test_the_agent_may_make_as_many_calls_as_are_allowed_and_must_then_give_its_text(self):
        rig = Rig()
        handler = Handler()
        result = rig.run(reply([call("t", {}, "c1")]), reply([call("t", {}, "c2")]), reply([message("done")]), handler=handler, max_calls=2)
        self.assertEqual((len(handler.calls), result.text, len(result.calls)), (2, "done", 2))
        self.assertEqual([c.get("refused") for c in result.calls], [None, None], "nothing was refused: the budget was not passed")

    def test_a_call_that_has_no_handler_to_answer_it_is_an_error_and_the_conversation_is_deleted(self):
        rig = Rig()
        with self.assertRaises(FoundryError) as raised:
            rig.run(reply([call("t", {}, "c1")]))
        self.assertIn("no handler", str(raised.exception))
        self.assertEqual(rig.service.conversations, {})

    def test_the_text_of_the_last_answer_is_the_text_and_parts_and_messages_are_joined(self):
        rig = Rig()
        two_parts = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "one"}, {"type": "output_text", "text": "two"}]}
        self.assertEqual(rig.run(reply([reasoning(), two_parts, message("three")])).text, "one\ntwo\nthree")

    def test_a_missing_usage_counts_as_nothing_and_a_missing_part_of_it_too(self):
        for usage_given, expected in (({"omit": True}, (0, 0)), ({"input_tokens": 7}, (7, 0)), ({"output_tokens": 9}, (0, 9)), (None, (0, 0))):
            with self.subTest(usage=usage_given):
                rig = Rig()
                document = reply([message("x")])
                if usage_given == {"omit": True}:
                    del document["usage"]
                else:
                    document["usage"] = usage_given
                result = rig.run(document)
                self.assertEqual((result.input_tokens, result.output_tokens), expected)


class SoftBudget(unittest.TestCase):
    """max_calls is a soft budget: the calls after it are answered without the handler, and the agent has three more rounds to give its text. The deadline is hard."""

    REFUSED = '{"error":"budget-used-up"}'

    @staticmethod
    def asks(*ids, tokens=(10, 5)):
        """An answer in which the agent asks for one tool call for each id."""
        return reply([call("t", {"n": each}, each) for each in ids], *tokens)

    @staticmethod
    def posted(rig):
        """What each request of the run carried as input, in order."""
        return [body["input"] for body in rig.service.responses]

    def test_the_words_of_the_refusal_and_the_number_of_extra_rounds_are_the_ones_that_were_fixed(self):
        self.assertEqual((fo.BUDGET_USED_UP, fo.GRACE_ROUNDS), ('{"error":"budget-used-up"}', 3))
        self.assertEqual(json.loads(fo.BUDGET_USED_UP), {"error": "budget-used-up"})

    def test_a_call_after_the_budget_is_answered_without_the_handler_and_the_agent_may_then_give_its_text(self):
        rig = Rig()
        handler = Handler('{"a":1}', '{"b":2}')
        result = rig.run(self.asks("c1"), self.asks("c2", tokens=(20, 6)), self.asks("c3", tokens=(30, 7)), reply([message("final")], 40, 8), handler=handler, max_calls=2)
        self.assertEqual((result.text, result.responses, (result.input_tokens, result.output_tokens)), ("final", 4, (100, 26)))
        self.assertEqual(handler.calls, [("t", {"n": "c1"}), ("t", {"n": "c2"})])
        self.assertEqual(self.posted(rig), [[], [output_of("c1", '{"a":1}')], [output_of("c2", '{"b":2}')], [output_of("c3", self.REFUSED)]])
        self.assertEqual(result.calls, [{"name": "t", "arguments": {"n": "c1"}, "ok": True, "chars": 7}, {"name": "t", "arguments": {"n": "c2"}, "ok": True, "chars": 7},
                                        {"name": "t", "arguments": {"n": "c3"}, "ok": False, "chars": len(self.REFUSED), "refused": True}])
        self.assertEqual((rig.service.routes()[-1], rig.service.conversations, rig.foundry.notes), ("DELETE conversation", {}, []))

    def test_the_agent_may_ask_again_in_three_rounds_after_the_first_refusal_and_still_give_its_text(self):
        for per_round in (1, 3):
            for asked_again in (0, 1, 2, 3):
                with self.subTest(calls_in_a_round=per_round, rounds_that_ask_again=asked_again):
                    rig = Rig()
                    handler = Handler()
                    again = [self.asks(*[f"x{i}_{j}" for j in range(per_round)]) for i in range(asked_again)]
                    result = rig.run(self.asks("c1"), self.asks("c2"), *again, reply([message("final")]), handler=handler, max_calls=2)
                    self.assertEqual((result.text, result.responses, len(handler.calls), len(result.calls)), ("final", 3 + asked_again, 2, 2 + asked_again * per_round))
                    self.assertEqual(rig.service.replies, [], "every answer was read, and none was asked for in vain")

    def test_an_agent_that_still_asks_after_the_three_more_rounds_is_a_failure_that_keeps_what_was_gathered(self):
        for per_round in (1, 3):
            with self.subTest(calls_in_a_round=per_round):
                rig = Rig()
                handler = Handler()
                again = [self.asks(*[f"x{i}_{j}" for j in range(per_round)], tokens=(30, 3)) for i in range(4)]
                with self.assertRaises(FoundryError) as raised:
                    rig.run(self.asks("c1", tokens=(10, 1)), self.asks("c2", tokens=(20, 2)), *again, reply([message("never read")]), handler=handler, max_calls=2)
                self.assertEqual(str(raised.exception), "Foundry run stopped: the budget of 2 tool calls was used up and the agent still asked for a tool call after "
                                                        "3 more rounds, and gave no text")
                self.assertIsNone(raised.exception.status)
                self.assertEqual(len(handler.calls), 2)
                self.assertEqual(len(rig.service.responses), 6, "no seventh answer is asked for")
                self.assertEqual(len(rig.service.replies), 1, "the text that was never asked for is never read")
                partial = raised.exception.partial
                self.assertEqual((partial.responses, partial.input_tokens, partial.output_tokens, partial.text), (6, 10 + 20 + 4 * 30, 1 + 2 + 4 * 3, ""))
                self.assertEqual([bool(c.get("refused")) for c in partial.calls], [False, False] + [True] * (4 * per_round))
                self.assertEqual([each[0]["call_id"] for each in self.posted(rig)[3:]], ["x0_0", "x1_0", "x2_0"], "the last round raised before it was answered")
                self.assertEqual((rig.service.routes()[-1], rig.service.conversations), ("DELETE conversation", {}))

    def test_the_round_that_crosses_the_budget_is_the_first_of_the_refusals(self):
        for asked_again, fails in ((2, False), (3, True)):
            with self.subTest(rounds_that_ask_again=asked_again):
                rig = Rig()
                crossing = reply([call("t", {}, "c2"), call("t", {}, "c3")])
                replies = [self.asks("c1"), crossing, *[self.asks(f"x{i}") for i in range(asked_again)], reply([message("final")])]
                if fails:
                    with self.assertRaises(FoundryError) as raised:
                        rig.run(*replies, handler=Handler(), max_calls=2)
                    self.assertIn("after 3 more rounds", str(raised.exception))
                else:
                    self.assertEqual(rig.run(*replies, handler=Handler(), max_calls=2).text, "final")

    def test_the_handler_runs_as_many_calls_as_the_budget_and_not_one_more(self):
        for budget in (0, 1, 2, 5, 24):
            with self.subTest(budget=budget):
                rig = Rig()
                handler = Handler()
                result = rig.run(*[self.asks(f"c{i}") for i in range(budget + 3)], reply([message("final")]), handler=handler, max_calls=budget)
                self.assertEqual((result.text, len(handler.calls), len(result.calls)), ("final", budget, budget + 3))
                self.assertEqual([bool(c.get("refused")) for c in result.calls], [False] * budget + [True] * 3)

    def test_a_batch_that_crosses_the_budget_runs_its_calls_up_to_it_and_refuses_the_rest_in_order(self):
        rig = Rig()
        handler = Handler('{"n":1}', '{"n":2}')
        crossing = reply([call("t", {"n": 2}, "c2"), call("u", {"n": 3}, "c3"), call("v", "not json", "c4")])
        result = rig.run(self.asks("c1"), crossing, reply([message("final")]), handler=handler, max_calls=2)
        self.assertEqual(handler.calls, [("t", {"n": "c1"}), ("t", {"n": 2})])
        self.assertEqual(rig.service.responses[2]["input"], [output_of("c2", '{"n":2}'), output_of("c3", self.REFUSED), output_of("c4", self.REFUSED)])
        self.assertEqual(result.calls[1:], [{"name": "t", "arguments": {"n": 2}, "ok": True, "chars": 7},
                                            {"name": "u", "arguments": {"n": 3}, "ok": False, "chars": len(self.REFUSED), "refused": True},
                                            {"name": "v", "arguments": {}, "ok": False, "chars": len(self.REFUSED), "refused": True}])
        self.assertEqual(result.text, "final")

    def test_with_no_calls_allowed_the_text_may_come_at_once_and_each_call_is_refused(self):
        rig = Rig()
        self.assertEqual(rig.run(reply([message("at once")]), handler=Handler(), max_calls=0).text, "at once")
        self.assertEqual(rig.service.routes(), ["POST conversations", "POST responses", "DELETE conversation"])
        rig = Rig()
        handler = Handler()
        result = rig.run(self.asks("c1"), reply([message("final")]), handler=handler, max_calls=0)
        self.assertEqual((result.text, handler.calls, [bool(c.get("refused")) for c in result.calls]), ("final", [], [True]))
        self.assertEqual(rig.service.responses[1]["input"], [output_of("c1", self.REFUSED)])

    def test_several_calls_after_the_budget_are_all_answered_in_one_input_list_and_a_message_beside_them_is_not_the_text(self):
        rig = Rig()
        handler = Handler()
        crowd = reply([call("a", {"x": 1}, "c2"), message("thinking aloud"), call("b", "[1]", "c3"), call("c", "{}", "c4")])
        result = rig.run(self.asks("c1"), crowd, reply([message("final")]), handler=handler, max_calls=1)
        self.assertEqual(len(handler.calls), 1)
        self.assertEqual(len(rig.service.responses), 3, "one request for the three answers")
        self.assertEqual(rig.service.responses[2]["input"], [output_of(each, self.REFUSED) for each in ("c2", "c3", "c4")])
        self.assertEqual([(c["name"], c["arguments"]) for c in result.calls[1:]], [("a", {"x": 1}), ("b", {}), ("c", {})])
        self.assertEqual(result.text, "final")

    def test_a_refused_call_is_recorded_without_arguments_when_they_are_not_an_object_and_the_budget_is_still_the_answer(self):
        for arguments in ("", "not json", "[1, 2]", "5", '"text"', "null", "true", "{", '{"a":', "[" * 5000):
            with self.subTest(arguments=arguments[:20]):
                rig = Rig()
                handler = Handler()
                result = rig.run(reply([call("t", arguments, "c1")]), reply([message("fine")]), handler=handler, max_calls=0)
                self.assertEqual(handler.calls, [])
                self.assertEqual(rig.service.responses[1]["input"], [output_of("c1", self.REFUSED)], "the budget is the answer, not bad-arguments")
                self.assertEqual(result.calls, [{"name": "t", "arguments": {}, "ok": False, "chars": len(self.REFUSED), "refused": True}])

    def test_a_call_that_failed_or_had_bad_arguments_counts_against_the_budget_like_any_other(self):
        rig = Rig()
        handler = Handler(RuntimeError("SECRET-DETAIL"))
        result = rig.run(self.asks("c1"), reply([call("t", "not json", "c2")]), self.asks("c3"), reply([message("final")]), handler=handler, max_calls=2)
        self.assertEqual(len(handler.calls), 1, "the second call never reached the handler: its arguments were not an object")
        self.assertEqual(self.posted(rig)[1:], [[output_of("c1", '{"error":"tool-failed"}')], [output_of("c2", '{"error":"bad-arguments"}')], [output_of("c3", self.REFUSED)]])
        self.assertEqual([c.get("refused") for c in result.calls], [None, None, True])
        self.assertEqual(result.text, "final")

    def test_the_results_of_the_extra_rounds_are_the_fixed_error_and_nothing_of_the_handler(self):
        rig = Rig()
        handler = Handler("HANDLER-RESULT-4471")
        result = rig.run(self.asks("c1"), *[self.asks(f"x{i}", f"y{i}") for i in range(3)], reply([message("final")]), handler=handler, max_calls=1)
        self.assertEqual(result.text, "final")
        refusals = [item for each in self.posted(rig)[2:] for item in each]
        self.assertEqual(refusals, [output_of(each, self.REFUSED) for each in ("x0", "y0", "x1", "y1", "x2", "y2")])
        self.assertEqual([json.loads(item["output"]) for item in refusals], [{"error": "budget-used-up"}] * 6)
        self.assertIn("HANDLER-RESULT-4471", json.dumps(self.posted(rig)[1]), "the one call that was run was answered by the handler")
        self.assertNotIn("HANDLER-RESULT-4471", json.dumps(self.posted(rig)[2:]))

    def test_the_deadline_stays_hard_in_the_extra_rounds_and_the_error_keeps_what_was_gathered(self):
        rig = Rig()
        rig.service.advance = 10
        handler = Handler()
        with self.assertRaises(FoundryError) as raised:
            rig.run(self.asks("c1"), self.asks("c2"), self.asks("c3"), self.asks("c4"), reply([message("late")]), handler=handler, max_calls=1, max_seconds=35)
        self.assertEqual(str(raised.exception), "Foundry run stopped: the time allowed (35 seconds) was used up after 1 tool calls and 2 that were refused")
        partial = raised.exception.partial
        self.assertEqual((partial.responses, partial.input_tokens, partial.output_tokens, partial.text), (3, 30, 15, ""))
        self.assertEqual([bool(c.get("refused")) for c in partial.calls], [False, True, True])
        self.assertEqual(len(handler.calls), 1)
        self.assertEqual((rig.service.routes()[-1], rig.service.conversations), ("DELETE conversation", {}))

    def test_a_call_after_70_percent_of_the_time_is_refused_like_one_beyond_the_budget_and_the_agent_may_still_give_its_text(self):
        self.assertEqual(fo.SOFT_TIME_SHARE, 0.7)
        rig = Rig()
        rig.service.advance = 10  # the conversation is made at 10 seconds, the first response comes at 20, the sixth at 70 (the soft time of 100 seconds) and the text at 80
        handler = Handler()
        result = rig.run(*[self.asks(f"c{i}") for i in range(1, 7)], reply([message("final")]), handler=handler, max_calls=40, max_seconds=100)
        self.assertEqual((result.text, result.out_of_time, len(handler.calls)), ("final", True, 5))
        self.assertEqual([c.get("refused") for c in result.calls], [None] * 5 + [True])
        self.assertEqual(self.posted(rig)[-1], [output_of("c6", self.REFUSED)])
        self.assertEqual((rig.service.routes()[-1], rig.service.conversations, rig.foundry.notes), ("DELETE conversation", {}, []))

    def test_a_run_that_is_not_late_and_within_its_budget_is_never_out_of_time_and_a_budget_that_ends_first_is_not_the_time(self):
        rig = Rig()
        rig.service.advance = 10
        result = rig.run(self.asks("c1"), self.asks("c2"), reply([message("final")]), handler=Handler(), max_calls=40, max_seconds=1000)
        self.assertEqual((result.out_of_time, [c.get("refused") for c in result.calls]), (False, [None, None]))
        rig = Rig()
        rig.service.advance = 10
        result = rig.run(self.asks("c1"), self.asks("c2"), reply([message("final")]), handler=Handler(), max_calls=1, max_seconds=1000)
        self.assertEqual((result.out_of_time, [c.get("refused") for c in result.calls]), (False, [None, True]), "the budget refused it")
        rig = Rig()
        rig.service.advance = 10
        result = rig.run(*[self.asks(f"c{i}") for i in range(1, 4)], reply([message("final")]), handler=Handler(), max_calls=1, max_seconds=100)
        self.assertEqual((result.out_of_time, [c.get("refused") for c in result.calls]), (False, [None, True, True]), "a call that the budget refused is not one that the time refused")

    def test_a_run_without_seconds_has_no_soft_time(self):
        rig = Rig()
        rig.service.advance = 10_000
        result = rig.run(self.asks("c1"), self.asks("c2"), reply([message("final")]), handler=Handler(), max_calls=40)
        self.assertEqual((result.out_of_time, [c.get("refused") for c in result.calls]), (False, [None, None]))

    def test_the_soft_time_counts_the_seconds_that_a_tool_took(self):
        rig = Rig()
        rig.service.advance = 1

        def slow(name, arguments):
            rig.clock.now += 80
            return "{}"

        result = rig.run(self.asks("c1"), self.asks("c2"), reply([message("final")]), handler=slow, max_calls=40, max_seconds=100)
        self.assertEqual(([c.get("refused") for c in result.calls], result.out_of_time, result.text), ([None, True], True, "final"))

    def test_an_agent_that_still_asks_after_the_soft_time_and_three_more_rounds_fails_with_words_about_the_time_and_keeps_what_was_gathered(self):
        rig = Rig()
        rig.service.advance = 1

        def slow(name, arguments):
            rig.clock.now += 80
            return "{}"

        with self.assertRaises(FoundryError) as raised:
            rig.run(*[self.asks(f"c{i}") for i in range(1, 8)], reply([message("never read")]), handler=slow, max_calls=40, max_seconds=100)
        self.assertEqual(str(raised.exception), "Foundry run stopped: the time for tool calls (70 seconds) was used up and the agent still asked for a tool call after "
                                                "3 more rounds, and gave no text")
        partial = raised.exception.partial
        self.assertEqual(([bool(c.get("refused")) for c in partial.calls], partial.out_of_time), ([False] + [True] * 4, True))
        self.assertEqual((rig.service.routes()[-1], rig.service.conversations), ("DELETE conversation", {}))


class Shapes(unittest.TestCase):
    """What the client refuses to read: each of these is a FoundryError that says what was asked and what is wrong, and the conversation is deleted."""

    def refused(self, document, contains, handler=None):
        rig = Rig()
        with self.assertRaises(FoundryError) as raised:
            rig.run(document, handler=handler or Handler())
        self.assertIn(contains, str(raised.exception))
        self.assertTrue(str(raised.exception).startswith("Foundry response failed"), str(raised.exception))
        self.assertEqual(rig.service.conversations, {})
        return raised.exception

    def test_an_answer_that_is_not_an_object_or_has_no_list_of_items(self):
        rig = Rig()
        for answer in ([], "text", 5, None, b"not json", b""):
            with self.subTest(answer=answer):
                rig = Rig()
                with self.assertRaises(FoundryError):
                    rig.run((200, answer))
        for output in (None, "text", {}, [1], ["x"], [{}], [{"type": 5}], [{"type": "message"}, 3]):
            with self.subTest(output=output):
                document = reply([message("x")])
                document["output"] = output
                self.refused(document, "no list of output items")
        document = reply([message("x")])
        del document["output"]
        self.refused(document, "no list of output items")

    def test_an_item_of_a_kind_that_the_app_does_not_use_is_an_error_that_names_the_kind(self):
        error = self.refused(reply([{"type": "web_search_call", "id": "ws_1"}, message("x")]), "a kind that this app does not use (web_search_call)")
        self.assertIsNone(error.status)
        self.refused(reply([{"type": "weird kind!", "id": "x"}]), "a kind that this app does not use")
        self.assertNotIn("weird", str(self.refused(reply([{"type": "weird kind!", "id": "x"}]), "does not use")))

    def test_a_function_call_that_is_not_valid(self):
        good = call("t", {}, "c1")
        bad = {"no call id": {**good, "call_id": None}, "an empty call id": {**good, "call_id": ""}, "a call id that is not text": {**good, "call_id": 5},
               "a call id of 65 characters": {**good, "call_id": "c" * 65}, "no name": {**good, "name": None}, "an empty name": {**good, "name": ""},
               "a name of 129 characters": {**good, "name": "n" * 129}, "arguments that are an object": {**good, "arguments": {"a": 1}}, "no arguments": {k: v for k, v in good.items() if k != "arguments"},
               "arguments that are null": {**good, "arguments": None}}
        for what, item in bad.items():
            with self.subTest(what):
                self.refused(reply([item]), "a function call of the answer is not valid")
        self.refused(reply([call("a", {}, "same"), call("b", {}, "same")]), "a function call of the answer is not valid")
        rig = Rig()
        rig.run(reply([call("n" * 128, {}, "c" * 64)]), reply([message("ok")]), handler=Handler())

    def test_a_message_that_is_not_one_of_the_agent_or_holds_something_else_than_text(self):
        wrong_role = {"type": "message", "role": "user", "content": [{"type": "output_text", "text": "x"}]}
        self.refused(reply([wrong_role]), "not one of the agent")
        self.refused(reply([{"type": "message", "role": "assistant", "content": "plain text"}]), "not one of the agent")
        self.refused(reply([{"type": "message", "role": "assistant", "content": None}]), "not one of the agent")
        for part in ({"type": "output_audio"}, {"type": "output_text"}, {"type": "output_text", "text": 5}, "text", None, {}):
            with self.subTest(part=part):
                self.refused(reply([{"type": "message", "role": "assistant", "content": [part]}]), "content that this app does not use")

    def test_an_answer_without_text_and_a_refusal_are_errors_that_do_not_repeat_the_words_of_the_model(self):
        self.refused(reply([]), "holds no text")
        self.refused(reply([reasoning()]), "holds no text")
        self.refused(reply([message("")]), "holds no text")
        self.refused(reply([message(" \n\t ")]), "holds no text")
        error = self.refused(reply([{"type": "message", "role": "assistant", "content": [{"type": "refusal", "refusal": "I will not do SECRET-MODEL-WORDS"}]}]), "refused to answer")
        self.assertNotIn("SECRET-MODEL-WORDS", str(error))

    def test_the_types_of_a_message_are_the_one_that_the_api_sends_and_the_one_that_its_reference_names(self):
        for kind in ("message", "output_message"):
            rig = Rig()
            item = {**message("ok"), "type": kind}
            self.assertEqual(rig.run(reply([item])).text, "ok")

    def test_an_answer_that_did_not_complete_says_how_and_never_repeats_its_text(self):
        for status, extra, contains in (("failed", {}, "the response is failed"), ("cancelled", {}, "the response is cancelled"), ("queued", {}, "the response is queued"),
                                        ("in_progress", {}, "the response is in_progress"), ("incomplete", {"incomplete_details": {"reason": "max_output_tokens"}}, "incomplete (max_output_tokens)"),
                                        ("incomplete", {"incomplete_details": {"reason": "content_filter"}}, "incomplete (content_filter)"), ("incomplete", {}, "the response is incomplete"),
                                        ("incomplete", {"incomplete_details": {"reason": "SECRET-WORDS"}}, "the response is incomplete"), ("strange", {}, "in a state that this app does not know"),
                                        (5, {}, "in a state that this app does not know"), ({"x": 1}, {}, "in a state that this app does not know"), ([], {}, "in a state that this app does not know")):
            with self.subTest(status=status, extra=extra):
                error = self.refused(reply([message("PARTIAL-MODEL-TEXT")], status=status, **extra), contains)
                self.assertNotIn("PARTIAL-MODEL-TEXT", str(error))
                self.assertNotIn("SECRET-WORDS", str(error))
                self.assertNotIn("strange", str(error))

    def test_an_answer_with_a_status_that_is_missing_or_completed_is_read(self):
        for status in (None, "completed"):
            rig = Rig()
            document = reply([message("ok")])
            if status is None:
                del document["status"]
            self.assertEqual(rig.run(document).text, "ok")

    def test_an_answer_that_holds_an_error_gives_the_code_and_the_message_of_it_redacted(self):
        error = self.refused(reply([message("PARTIAL-MODEL-TEXT")], status="failed", error={"code": "server_error", "message": f"boom {JWT} and more"}), "the response failed; server_error: boom")
        text = str(error)
        self.assertIn("[redacted]", text)
        self.assertNotIn(JWT, text)
        self.assertNotIn("PARTIAL-MODEL-TEXT", text)
        self.refused(reply([message("x")], error={"code": "x"}), "the response failed; x")
        self.refused(reply([message("x")], error="text"), "the response failed")
        self.assertNotIn("; ", str(self.refused(reply([message("x")], error="text"), "the response failed")))

    def test_a_usage_that_is_not_valid_is_an_error(self):
        for bad in ("text", [1], {"input_tokens": -1}, {"output_tokens": -1}, {"input_tokens": "5"}, {"output_tokens": 1.5}, {"input_tokens": True}, {"output_tokens": None},
                    {"input_tokens": 5, "output_tokens": -2}):
            with self.subTest(usage=bad):
                document = reply([message("x")])
                document["usage"] = bad
                self.refused(document, "a usage that is not valid")

    def test_a_conversation_id_that_could_not_be_put_in_an_address_is_refused_and_nothing_is_deleted(self):
        for identifier in ("../x", "conv_/../x", "conv_a/b", "conv_", "", 5, None, "conv_" + "a" * 101, "x", "conv_a?b", "conv_a b", "conv_a\n"):
            with self.subTest(identifier=identifier):
                rig = Rig()
                rig.service.failures["POST conversations"] = (200, {"id": identifier})
                with self.assertRaises(FoundryError) as raised:
                    rig.run(reply([message("x")]))
                self.assertIn("no conversation id that this app accepts", str(raised.exception))
                self.assertEqual(rig.service.routes(), ["POST conversations"])
        rig = Rig()
        rig.service.failures["POST conversations"] = (200, {})
        with self.assertRaises(FoundryError):
            rig.run(reply([message("x")]))
        rig = Rig()
        rig.service.failures["POST conversations"] = (200, {"id": "conv_" + "a" * 100})
        rig.service.failures["DELETE conversation"] = (200, {})
        self.assertEqual(rig.run(reply([message("x")])).text, "x")
        self.assertEqual(rig.service.calls[-1]["path"], "/openai/v1/conversations/conv_" + "a" * 100)


class Deadline(unittest.TestCase):
    def test_the_run_stops_when_its_seconds_are_used_up_and_each_call_gets_only_the_time_that_is_left(self):
        rig = Rig()
        rig.service.advance = 10
        handler = Handler()
        with mock.patch.object(fo, "SOFT_TIME_SHARE", 10.0):  # out of reach: the soft time has its own tests, and here the limit is the hard one
            with self.assertRaises(FoundryError) as raised:
                rig.run(reply([call("t", {}, "c1")]), reply([call("t", {}, "c2")]), reply([call("t", {}, "c3")]), reply([message("late")]), handler=handler, max_seconds=25)
        self.assertEqual(str(raised.exception), "Foundry run stopped: the time allowed (25 seconds) was used up after 2 tool calls")
        self.assertEqual(len(handler.calls), 2)
        partial = raised.exception.partial
        self.assertEqual((len(partial.calls), partial.responses, partial.input_tokens, partial.output_tokens), (2, 2, 20, 10), "what was gathered is kept")
        self.assertEqual([(c["route"], c["timeout"]) for c in rig.service.calls[:3]], [("POST conversations", 25), ("POST responses", 15), ("POST responses", 5)])
        self.assertEqual(rig.service.routes()[-1], "DELETE conversation")
        self.assertEqual(rig.service.conversations, {})
        self.assertIsNone(rig.client.deadline, "the deadline that the client had is put back")
        self.assertEqual(rig.lookup.calls, [], "no host name is looked up when the time is used up")

    def test_the_seconds_that_a_tool_took_count(self):
        rig = Rig()
        rig.service.advance = 1

        def slow(name, arguments):
            rig.clock.now += 500
            return "{}"

        with self.assertRaises(FoundryError) as raised:
            rig.run(reply([call("t", {}, "c1")]), reply([message("never read")]), handler=slow, max_seconds=100)
        self.assertIn("the time allowed (100 seconds)", str(raised.exception))
        self.assertEqual(len(rig.service.responses), 1, "no answer is asked for after the time is used up")
        partial = raised.exception.partial
        self.assertEqual(([(c["name"], c["ok"]) for c in partial.calls], partial.responses, (partial.input_tokens, partial.output_tokens)), ([("t", True)], 1, (10, 5)),
                         "the call that took the time is kept")

    def test_the_deadline_of_the_run_is_tightened_for_the_run_and_put_back_after_it(self):
        for before, during in ((None, 1050.0), (1020.0, 1020.0), (5000.0, 1050.0)):
            with self.subTest(before=before):
                rig = Rig()
                rig.client.deadline = before
                seen = []

                def handler(name, arguments):
                    seen.append(rig.client.deadline)
                    return "{}"

                rig.run(reply([call("t", {}, "c1")]), reply([message("fine")]), handler=handler, max_seconds=50)
                self.assertEqual(seen, [during])
                self.assertEqual(rig.client.deadline, before)
                self.assertEqual([c["deadline"] for c in rig.service.calls], [during, during, during, None], "and the clean-up is made without one")

    def test_without_seconds_the_deadline_of_the_client_is_left_alone(self):
        rig = Rig()
        rig.client.deadline = 4000.0
        rig.run(reply([message("fine")]))
        self.assertEqual([c["deadline"] for c in rig.service.calls], [4000.0, 4000.0, None])
        self.assertEqual(rig.client.deadline, 4000.0)

    def test_the_deadline_of_the_whole_run_stops_it_too_and_the_conversation_is_still_deleted(self):
        rig = Rig()
        rig.client.deadline = 1015.0
        rig.service.advance = 10
        with self.assertRaises(FoundryError) as raised:
            rig.run(reply([call("t", {}, "c1")]), reply([message("late")]), handler=Handler())
        self.assertEqual(str(raised.exception), "Foundry function output failed: the time allowed was used up")
        self.assertIsNone(raised.exception.status)
        partial = raised.exception.partial
        self.assertEqual(([c["name"] for c in partial.calls], partial.responses, (partial.input_tokens, partial.output_tokens), partial.text), (["t"], 1, (10, 5), ""),
                         "what was gathered before the time ran out is kept")
        self.assertEqual(rig.service.routes(), ["POST conversations", "POST responses", "DELETE conversation"])
        self.assertEqual(rig.client.deadline, 1015.0)
        self.assertEqual(rig.lookup.calls, [])

    def test_the_deadline_is_put_back_also_when_the_run_fails_in_the_middle(self):
        rig = Rig()
        rig.client.deadline = 3000.0
        with self.assertRaises(FoundryError):
            rig.run((500, {}), max_seconds=10)
        self.assertEqual(rig.client.deadline, 3000.0)
        rig = Rig()
        rig.service.failures["POST conversations"] = (400, {})
        with self.assertRaises(FoundryError):
            rig.run(max_seconds=10)
        self.assertIsNone(rig.client.deadline)


class Errors(unittest.TestCase):
    def failing(self, route, status, document, action="ensure"):
        rig = Rig()
        rig.service.failures[route] = (status, document)
        return rig

    def test_an_http_failure_says_what_was_asked_the_status_and_the_words_of_the_service(self):
        body = {"error": {"code": "invalid_request_error", "message": "The model deployment 'gpt-x' does not exist."}}
        text = "Foundry {} failed: HTTP 400; invalid_request_error: The model deployment 'gpt-x' does not exist."
        cases = []

        rig = Rig()
        rig.service.failures["GET agent"] = (400, body)
        cases.append(("read agent", rig, lambda: rig.foundry.ensure_agent(spec())))
        rig = Rig()
        rig.service.failures["POST agents"] = (400, body)
        cases.append(("create agent", rig, lambda: rig.foundry.ensure_agent(spec())))
        rig = Rig()
        rig.foundry.ensure_agent(spec())
        rig.service.failures["POST versions"] = (400, body)
        cases.append(("new version", rig, lambda: rig.foundry.ensure_agent(spec(model="gpt-6-luna"))))
        rig = Rig()
        rig.service.failures["POST conversations"] = (400, body)
        cases.append(("create conversation", rig, lambda: rig.run(reply([message("x")]))))
        rig = Rig()
        cases.append(("response", rig, lambda: rig.run((400, body), (400, body))))  # the first call is made again with the other key, and fails again
        rig = Rig()
        cases.append(("function output", rig, lambda: rig.run(reply([call("t", {}, "c1")]), (400, body), handler=Handler())))
        for purpose, rig, action in cases:
            with self.subTest(purpose):
                with self.assertRaises(FoundryError) as raised:
                    action()
                self.assertEqual(str(raised.exception), text.format(purpose))
                self.assertEqual(raised.exception.status, 400)

    def test_the_words_of_the_service_are_its_code_and_its_message_or_what_there_is_of_them(self):
        for error, words in (({"code": "X", "message": "Y"}, "X: Y"), ({"code": "X"}, "X"), ({"message": "Y"}, "Y"), ({"code": 429, "message": "slow"}, "429: slow"),
                             ({"code": True, "message": "Y"}, "Y"), ({"code": {"a": 1}, "message": ["b"]}, ""), ({"code": "", "message": "  "}, ""), ({}, ""), ("text", ""), (None, ""),
                             ({"code": "Bad\nCode", "message": "m"}, "Bad Code: m")):
            with self.subTest(error=error):
                rig = Rig()
                rig.service.failures["POST agents"] = (400, {"error": error})
                with self.assertRaises(FoundryError) as raised:
                    rig.foundry.ensure_agent(spec())
                self.assertEqual(str(raised.exception), "Foundry create agent failed: HTTP 400" + (f"; {words}" if words else ""))

    def test_a_body_without_an_error_object_adds_nothing(self):
        for body in ({"message": "TOP-LEVEL-WORDS"}, {"statusCode": 400, "message": "TOP-LEVEL-WORDS"}, [], "TOP-LEVEL-WORDS", b"<html>TOP-LEVEL-WORDS</html>", b"", b"\xff\xfe\x00", b"{"):
            with self.subTest(body=body):
                rig = Rig()
                rig.service.failures["POST agents"] = (400, body)
                with self.assertRaises(FoundryError) as raised:
                    rig.foundry.ensure_agent(spec())
                self.assertEqual(str(raised.exception), "Foundry create agent failed: HTTP 400")

    def test_a_body_that_is_too_deep_to_be_parsed_is_an_error_of_the_client_too(self):
        deep = b"[" * 5000
        for status, text in ((400, "Foundry create agent failed: HTTP 400"), (200, "Foundry create agent failed: the answer is not JSON")):
            with self.subTest(status=status):
                rig = Rig()
                rig.service.failures["POST agents"] = (status, deep)
                with self.assertRaises(FoundryError) as raised:
                    rig.foundry.ensure_agent(spec())
                self.assertEqual((str(raised.exception), raised.exception.status), (text, status))
                self.assertIsNone(rig.client.deadline)
                self.assertIs(rig.client.transport, rig.service, "the transport of the client is put back")

    def test_the_message_is_cut_to_200_characters_with_its_code(self):
        rig = Rig()
        rig.service.failures["POST agents"] = (400, {"error": {"code": "c", "message": "m" * 500}})
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        words = str(raised.exception).split("; ", 1)[1]
        self.assertEqual((len(words), words), (200, "c: " + "m" * 197))

    def test_control_characters_are_removed_and_white_space_is_one_space(self):
        rig = Rig()
        message_text = "first\nsecond\tthird\x00\x1b[31m red \x07\u202e\u200bend\r\n  \u00a0 last \ud800"
        rig.service.failures["POST agents"] = (400, {"error": {"code": "c", "message": message_text}})
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        text = str(raised.exception)
        self.assertEqual(text, "Foundry create agent failed: HTTP 400; c: first second third[31m red end last")
        self.assertTrue(all(ch.isprintable() for ch in text))

    def test_a_token_like_string_in_an_error_body_comes_out_redacted_whatever_its_shape(self):
        message_text = f"The token {JWT} and Bearer abcdefgh12345678 and api-key: SECRETKEYVALUE and {TOKEN} are not valid"
        for route, status in (("GET agent", 401), ("POST agents", 400), ("GET agent", 403)):
            with self.subTest(route=route, status=status):
                rig = Rig()
                rig.service.failures[route] = (status, {"error": {"code": f"Invalid-{JWT}", "message": message_text}})
                with self.assertRaises(FoundryError) as raised:
                    rig.foundry.ensure_agent(spec())
                text = str(raised.exception)
                for secret in (JWT, "abcdefgh12345678", "SECRETKEYVALUE", TOKEN, "eyJhbGciOiJSUzI1NiJ9"):
                    self.assertNotIn(secret, text)
                self.assertIn("[redacted]", text)
                self.assertIn("The token", text)
                self.assertEqual(text.count("[redacted]"), 5)

    def test_a_token_that_the_cut_would_have_split_is_redacted_as_a_whole(self):
        # The token starts at character 150 of the words and goes past the cut at 200: a cut before the redaction would leave the front of it (two parts of three).
        message_text = "m" * 147 + " " + JWT + " tail"
        rig = Rig()
        rig.service.failures["POST agents"] = (400, {"error": {"code": "c", "message": message_text}})
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        text = str(raised.exception)
        self.assertNotIn("eyJ", text)
        self.assertNotIn(JWT[:40], text)
        self.assertIn("[redacted]", text)
        self.assertLessEqual(len(text.split("; ", 1)[1]), 200)

    def test_a_token_with_a_control_character_inside_is_redacted_too(self):
        rig = Rig()
        rig.service.failures["POST agents"] = (400, {"error": {"code": "c", "message": f"token {TOKEN[:20]}\x00{TOKEN[20:]} end"}})
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        self.assertNotIn(TOKEN[:20], str(raised.exception))
        self.assertNotIn(TOKEN[20:], str(raised.exception))
        self.assertNotIn(TOKEN[:20], raised.exception.words, "the words that the error keeps are clean too")
        self.assertNotIn(TOKEN[20:], raised.exception.words)

    def test_the_token_is_registered_for_redaction_when_it_is_asked_for(self):
        rig = Rig()
        rig.service.replies = [reply([message("x")])]
        self.assertEqual(rig.redact(f"a {TOKEN} b"), f"a {TOKEN} b")
        rig.foundry.run(AGENT, "Go.")
        self.assertEqual(rig.redact(f"a {TOKEN} b"), "a [redacted] b")

    def test_nothing_of_the_request_the_token_or_the_model_is_in_an_error_except_what_the_service_itself_said(self):
        rig = Rig()
        handler = Handler('{"secret":"SECRET-TOOL-OUTPUT"}')
        with self.assertRaises(FoundryError) as raised:
            rig.run(reply([call("t", {"arg": "SECRET-ARGUMENTS"}, "c1")]), (400, {"error": {"code": "bad", "message": "no"}}), handler=handler)
        text = str(raised.exception)
        self.assertEqual(text, "Foundry function output failed: HTTP 400; bad: no")
        for secret in ("SECRET-TOOL-OUTPUT", "SECRET-ARGUMENTS", TOKEN, "Bearer", "Look at the estate", "c1", "conv_"):
            self.assertNotIn(secret, text)
        self.assertEqual(raised.exception.partial.calls[0]["arguments"], {"arg": "SECRET-ARGUMENTS"})

    def test_the_error_has_no_cause_to_print_and_a_traceback_holds_the_sanitized_text_only(self):
        # The client's own text of the error cuts the body before it redacts it, so it is not the text of this error and it is not printed with it.
        message_text = "m" * 150 + " " + JWT
        rig = Rig()
        rig.service.failures["POST agents"] = (400, {"error": {"code": "c", "message": message_text}})
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        self.assertIsNone(raised.exception.__cause__)
        self.assertTrue(raised.exception.__suppress_context__)
        printed = "".join(traceback.format_exception(raised.exception))
        self.assertNotIn("eyJ", printed)

    def test_a_failure_to_get_a_token_is_an_error_of_the_client_and_no_call_is_made(self):
        rig = Rig(token=IdentityError("the platform's managed identity endpoint is not available"))
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        self.assertEqual(str(raised.exception), "Foundry read agent failed: no token could be had for the service (the platform's managed identity endpoint is not available)")
        self.assertEqual(rig.service.calls, [])

    def test_a_client_without_the_calls_of_the_project_is_refused_by_its_list_and_says_which_call(self):
        rig = Rig(allowed=http.allowed_calls())
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        self.assertEqual(str(raised.exception), f"Foundry read agent failed: the app makes no GET call to {HOST}{PROJECT}/agents/{NAME}"[:150])
        self.assertEqual(rig.service.calls, [])

    def test_an_answer_that_is_not_json_or_not_an_object_is_an_error_with_the_status_of_the_answer(self):
        for answer in (b"not json", b"[1]", b'"text"', b"", b"null"):
            with self.subTest(answer=answer):
                rig = Rig()
                rig.service.failures["POST agents"] = (200, answer)
                with self.assertRaises(FoundryError) as raised:
                    rig.foundry.ensure_agent(spec())
                self.assertRegex(str(raised.exception), r"^Foundry create agent failed: the answer is not (JSON|a JSON object)$")
                self.assertEqual(raised.exception.status, 200)

    def test_the_status_is_kept_on_the_error_and_a_failure_without_an_answer_has_none(self):
        for failure, status in (((409, {}), 409), (urllib.error.URLError("down"), None)):
            rig = Rig()
            rig.service.failures["POST agents"] = failure
            with self.assertRaises(FoundryError) as raised:
                rig.foundry.ensure_agent(spec())
            self.assertEqual(raised.exception.status, status)

    def test_the_words_are_those_of_the_last_answer_when_the_call_was_made_again(self):
        rig = Rig()
        rig.service.failures["GET agent"] = [(503, {"error": {"code": "first", "message": "one"}}), (503, {"error": {"code": "second", "message": "two"}}),
                                             (502, {"error": {"code": "third", "message": "three"}})]
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        self.assertEqual(str(raised.exception), "Foundry read agent failed: HTTP 502; third: three")
        self.assertEqual(len(rig.service.calls), 3)
        self.assertIs(rig.client.transport, rig.service, "the transport of the client is put back")

    def test_the_words_of_a_failure_without_an_answer_are_not_taken_from_an_earlier_answer(self):
        rig = Rig()
        rig.service.failures["GET agent"] = [(503, {"error": {"code": "first", "message": "one"}}), urllib.error.URLError("down"), urllib.error.URLError("down")]
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        self.assertEqual(str(raised.exception), "Foundry read agent failed: no answer (the connection failed or timed out); DNS of the endpoint host: private")

    def test_the_partial_run_is_kept_on_the_error_of_a_run_and_an_agent_has_none(self):
        rig = Rig()
        with self.assertRaises(FoundryError) as raised:
            rig.run(reply([call("t", {}, "c1")], 11, 3), (500, {}), handler=Handler('{"a":1}'))
        partial = raised.exception.partial
        self.assertEqual((partial.responses, partial.input_tokens, partial.output_tokens, partial.text), (1, 11, 3, ""))
        self.assertEqual(partial.calls, [{"name": "t", "arguments": {}, "ok": True, "chars": 7}])
        rig = Rig()
        rig.service.failures["POST conversations"] = (500, {})
        with self.assertRaises(FoundryError) as raised:
            rig.run()
        partial = raised.exception.partial
        self.assertEqual((partial.calls, partial.responses, partial.text), ([], 0, ""), "a run that failed at once has an empty partial run, not none")
        rig = Rig()
        rig.service.failures["POST agents"] = (400, {})
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        self.assertIsNone(raised.exception.partial)


class Cleanup(unittest.TestCase):
    def test_the_conversation_is_deleted_after_every_kind_of_failure(self):
        runs = {
            "an error of the service": lambda rig: rig.run((500, {})), "an answer that cannot be read": lambda rig: rig.run(reply([{"type": "strange_kind"}])),
            "no text": lambda rig: rig.run(reply([])),
            "calls that go on after the budget and the extra rounds": lambda rig: rig.run(*[reply([call("t", {}, f"c{i}")]) for i in range(4)], handler=Handler(), max_calls=0),
            "no handler": lambda rig: rig.run(reply([call("t", {}, "c1")])), "no answer at all": lambda rig: rig.run(urllib.error.URLError("down")),
        }
        for what, action in runs.items():
            with self.subTest(what):
                rig = Rig()
                if what == "no answer at all":
                    rig.service.failures["POST responses"] = urllib.error.URLError("down")
                with self.assertRaises(FoundryError):
                    action(rig)
                self.assertEqual(rig.service.routes()[-1], "DELETE conversation")
                self.assertEqual(rig.service.conversations, {})

    def test_the_conversation_is_deleted_when_the_handler_stops_the_program_too(self):
        rig = Rig()
        with self.assertRaises(KeyboardInterrupt):
            rig.run(reply([call("t", {}, "c1")]), handler=Handler(KeyboardInterrupt()))
        self.assertEqual(rig.service.conversations, {})
        self.assertIsNone(rig.client.deadline)

    def test_a_conversation_that_was_never_made_is_not_deleted(self):
        rig = Rig()
        rig.service.failures["POST conversations"] = (500, {})
        with self.assertRaises(FoundryError):
            rig.run()
        self.assertEqual(rig.service.routes(), ["POST conversations"])

    def test_a_delete_that_fails_changes_neither_the_result_nor_the_error_and_leaves_a_note_and_a_log_line(self):
        marker = "FINAL-TEXT-OF-THE-MODEL-9917"
        rig = Rig()
        rig.service.failures["DELETE conversation"] = (500, {"error": {"code": "ServerError", "message": "nope"}})
        with LogCapture() as logs:
            result = rig.run(reply([message(marker)]))
        self.assertEqual(result.text, marker)
        expected = "Foundry delete conversation failed: HTTP 500; ServerError: nope"
        self.assertEqual(rig.foundry.notes, [expected])
        self.assertEqual([m for m in logs.messages() if "Foundry" in m], [expected])
        self.assertNotIn(marker, " ".join(rig.foundry.notes) + " ".join(logs.messages()))
        rig = Rig()
        rig.service.failures["DELETE conversation"] = (403, {"error": {"code": "PermissionDenied", "message": "no"}})
        with self.assertRaises(FoundryError) as raised:
            rig.run((500, {"error": {"code": "first", "message": "the first error"}}))
        self.assertEqual(str(raised.exception), "Foundry response failed: HTTP 500; first: the first error", "the error of the run is the one that is raised")
        self.assertEqual(rig.foundry.notes, ["Foundry delete conversation failed: HTTP 403; DNS of the endpoint host: private; PermissionDenied: no"])

    def test_a_delete_that_does_not_even_answer_or_cannot_be_asked_is_a_note_as_well(self):
        rig = Rig()
        rig.service.failures["DELETE conversation"] = urllib.error.URLError("down")
        result = rig.run(reply([message("x")]))
        self.assertEqual(result.text, "x")
        self.assertEqual(rig.foundry.notes, ["Foundry delete conversation failed: no answer (the connection failed or timed out); DNS of the endpoint host: private"])
        rig = Rig()
        rig.service.replies = [reply([message("x")])]
        original = rig.issue
        asked = []

        def token_that_fails_the_second_time(resource):
            asked.append(resource)
            if len(asked) > 2:
                raise RuntimeError("SECRET-DETAIL")
            return original(resource)

        rig.foundry.token = token_that_fails_the_second_time
        self.assertEqual(rig.foundry.run(AGENT, "Go.").text, "x")
        self.assertEqual(rig.foundry.notes, ["Foundry delete conversation failed: RuntimeError"])

    def test_a_conversation_that_is_already_gone_is_not_a_problem_and_no_host_is_looked_up(self):
        rig = Rig()
        rig.service.failures["DELETE conversation"] = (404, {"error": {"code": "not_found", "message": "gone"}})
        self.assertEqual(rig.run(reply([message("x")])).text, "x")
        self.assertEqual((rig.foundry.notes, rig.lookup.calls), ([], []))

    def test_the_notes_are_kept_for_a_few_problems_only(self):
        rig = Rig()
        rig.service.failures["DELETE conversation"] = (500, {})
        with LogCapture():
            for _ in range(fo.MAX_NOTES + 5):
                rig.run(reply([message("x")]))
        self.assertEqual(len(rig.foundry.notes), fo.MAX_NOTES)

    def test_the_delete_has_its_own_short_timeout_and_one_retry_at_most(self):
        rig = Rig()
        rig.service.failures["DELETE conversation"] = [(503, {}), PASS]
        rig.run(reply([message("x")]))
        deletes = [c for c in rig.service.calls if c["method"] == "DELETE"]
        self.assertEqual((len(deletes), deletes[0]["timeout"], rig.foundry.notes), (2, fo.CLEANUP_TIMEOUT, []))
        rig = Rig()
        rig.service.failures["DELETE conversation"] = (503, {})
        rig.run(reply([message("x")]))
        self.assertEqual(len([c for c in rig.service.calls if c["method"] == "DELETE"]), 2)
        self.assertEqual(len(rig.foundry.notes), 1)


class Repeats(unittest.TestCase):
    """What may be made again when its answer did not come: a read, always; a creation or a run, only when the service said "not now"."""

    def test_a_read_is_made_again_after_a_server_error_and_after_a_lost_connection(self):
        for first in ((503, {}), (500, {}), (502, {}), (504, {}), urllib.error.URLError("down"), TimeoutError("slow")):
            with self.subTest(first=first):
                rig = Rig()
                rig.service.failures["GET agent"] = [first, PASS]
                rig.service.agents[NAME] = [Service.version(NAME, {"definition": {}}, 1)]
                self.assertEqual(rig.foundry.ensure_agent(spec()), f"{NAME}:2")
                self.assertEqual(rig.service.routes()[:2], ["GET agent", "GET agent"])
                self.assertEqual(len(rig.sleeps), 1)

    def test_a_creation_is_not_made_again_when_it_may_have_been_carried_out(self):
        for route, setup in (("POST agents", lambda rig: None), ("POST versions", lambda rig: rig.foundry.ensure_agent(spec(model="gpt-6-luna")))):
            for first in ((500, {}), (502, {}), (504, {}), urllib.error.URLError("down"), TimeoutError("slow"), ConnectionResetError()):
                with self.subTest(route=route, first=first):
                    rig = Rig()
                    setup(rig)
                    rig.service.failures[route] = [first, PASS]
                    rig.service.calls.clear()
                    with self.assertRaises(FoundryError):
                        rig.foundry.ensure_agent(spec())
                    self.assertEqual(rig.service.routes().count(route), 1)

    def test_a_conversation_and_a_run_are_not_made_again_either(self):
        for route in ("POST conversations", "POST responses"):
            for first in ((500, {}), (502, {}), (504, {}), urllib.error.URLError("down"), TimeoutError("slow")):
                with self.subTest(route=route, first=first):
                    rig = Rig()
                    rig.service.failures[route] = [first, PASS]
                    with self.assertRaises(FoundryError):
                        rig.run(reply([message("x")]))
                    self.assertEqual(rig.service.routes().count(route), 1)

    def test_a_creation_a_conversation_and_a_run_are_made_again_when_the_service_says_not_now(self):
        for route, status in (("POST agents", 429), ("POST agents", 503), ("POST conversations", 429), ("POST responses", 503), ("POST responses", 429)):
            with self.subTest(route=route, status=status):
                rig = Rig()
                rig.service.failures[route] = [(status, {"retry-after": "2"}, {}), PASS]
                if route == "POST agents":
                    self.assertEqual(rig.foundry.ensure_agent(spec()), f"{NAME}:1")
                else:
                    self.assertEqual(rig.run(reply([message("x")])).text, "x")
                self.assertEqual(rig.service.routes().count(route), 2)
                # A 503 has no Retry-After here. It waits as long as a server error does, and a step of a run waits fo.RATE_BACKOFF seconds (with the jitter of 0.5) for its first repeat.
                waits_for_503 = 1.5 * fo.RATE_BACKOFF if route == "POST responses" else 1.5
                self.assertEqual(rig.sleeps, [2.0] if status == 429 else [waits_for_503], "a Retry-After header is obeyed for a 429")

    def test_a_step_of_a_run_waits_for_the_tokens_of_its_model_and_says_so(self):
        rig = Rig()
        slow = (429, {}, {"error": {"code": "rate_limit_exceeded", "message": "Model deployment rate limit exceeded."}})
        rig.service.failures["POST responses"] = [slow] * fo.RATE_RETRIES + [PASS]
        self.assertEqual(rig.run(reply([message("x")])).text, "x")
        self.assertEqual(rig.service.routes().count("POST responses"), fo.RATE_RETRIES + 1)
        self.assertEqual(rig.sleeps, [12.0, 24.0, 30.0, 30.0, 30.0, 30.0], "8 seconds, then 16 and 30 at most, each with the jitter of 0.5")
        self.assertEqual(rig.foundry.notes, [f"Foundry response: the service said not now (HTTP 429 or 503) {fo.RATE_RETRIES} times, and the call was made again after a pause"])
        bodies = [json.dumps(c["body"], sort_keys=True) for c in rig.service.calls if c["route"] == "POST responses"]
        self.assertEqual((len(bodies), len(set(bodies))), (fo.RATE_RETRIES + 1, 1), "the same input is sent again")

    def test_a_step_that_is_still_refused_after_the_repeats_is_an_error_with_its_status_and_no_function_output_is_lost_or_doubled(self):
        rig = Rig()
        rig.service.replies = [reply([call("t", {}, "c1")])]
        slow = (429, {}, {"error": {"code": "rate_limit_exceeded", "message": "Slow down"}})
        rig.service.failures["POST responses"] = [PASS] + [slow]
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.run(AGENT, "Go.", Handler('{"a":1}'))
        self.assertEqual(str(raised.exception), "Foundry function output failed: HTTP 429; rate_limit_exceeded: Slow down")
        self.assertEqual(len(rig.sleeps), fo.RATE_RETRIES)
        self.assertEqual(rig.service.routes().count("POST responses"), 1 + fo.RATE_RETRIES + 1)
        asked = [c["body"]["input"] for c in rig.service.calls if c["route"] == "POST responses"][1:]
        self.assertEqual([[item["call_id"] for item in each] for each in asked], [["c1"]] * (fo.RATE_RETRIES + 1), "the output of the call is sent again, once in each request")
        self.assertEqual(raised.exception.partial.calls, [{"name": "t", "arguments": {}, "ok": True, "chars": 7}])

    def test_a_retry_after_is_obeyed_up_to_the_wait_that_the_client_allows_and_a_longer_one_is_an_error(self):
        self.assertEqual(fo.RATE_WAIT_MAX, 90.0)
        for wait, repeated in (("90", True), ("91", False)):
            with self.subTest(wait=wait):
                rig = Rig()
                rig.service.failures["POST responses"] = [(429, {"retry-after": wait}, {"error": {"code": "rate_limit_exceeded", "message": "Slow down"}}), PASS]
                if repeated:
                    self.assertEqual(rig.run(reply([message("x")])).text, "x")
                    self.assertEqual(rig.sleeps, [90.0])
                else:
                    with self.assertRaises(FoundryError) as raised:
                        rig.run(reply([message("x")]))
                    self.assertEqual((raised.exception.status, rig.sleeps), (429, []))

    def test_the_pauses_of_a_step_stay_inside_the_time_of_the_run(self):
        rig = Rig()
        rig.client.sleep = lambda seconds: (rig.sleeps.append(seconds), setattr(rig.clock, "now", rig.clock.now + seconds))
        rig.service.failures["POST responses"] = (429, {}, {"error": {"code": "rate_limit_exceeded", "message": "Slow down"}})
        with self.assertRaises(FoundryError) as raised:
            rig.run(max_seconds=40)
        self.assertEqual(rig.sleeps, [12.0, 24.0], "the third pause of 30 seconds would end after the 40 seconds, so it is not taken")
        self.assertEqual(raised.exception.status, 429)
        self.assertEqual(rig.service.routes()[-1], "DELETE conversation")

    def test_the_other_calls_keep_their_two_repeats_and_say_nothing_of_them(self):
        for route in ("POST agents", "POST conversations"):
            with self.subTest(route=route):
                rig = Rig()
                rig.service.failures[route] = (503, {}, {})
                with self.assertRaises(FoundryError):
                    rig.foundry.ensure_agent(spec()) if route == "POST agents" else rig.run()
                self.assertEqual((rig.service.routes().count(route), rig.sleeps, rig.foundry.notes), (3, [1.5, 3.0], []))

    def test_the_run_asks_the_same_thing_again_and_a_long_wait_is_an_error_with_its_status(self):
        rig = Rig()
        rig.service.replies = [(503, {}), reply([message("x")])]
        rig.foundry.run(AGENT, "Go.")
        self.assertEqual(rig.service.responses[0], rig.service.responses[1])
        rig = Rig()
        rig.service.failures["POST responses"] = (429, {"retry-after": "3600"}, {"error": {"code": "rate_limit_exceeded", "message": "Slow down"}})
        with self.assertRaises(FoundryError) as raised:
            rig.run()
        self.assertEqual(str(raised.exception), "Foundry response failed: HTTP 429; rate_limit_exceeded: Slow down")
        self.assertEqual(rig.sleeps, [])

    def test_a_response_is_asked_for_with_the_long_timeout_and_the_other_calls_with_the_short_one(self):
        rig = Rig()
        rig.run(reply([message("x")]))
        self.assertEqual([(c["route"], c["timeout"]) for c in rig.service.calls],
                         [("POST conversations", 30), ("POST responses", fo.RESPONSE_TIMEOUT), ("DELETE conversation", fo.CLEANUP_TIMEOUT)])


class TheKeyOfTheAgent(unittest.TestCase):
    """The REST reference writes the key of the agent reference as agent_reference and the article on function calling as agent. The first response that the service
    answers, if it answers it with an HTTP 400 that is not about the model, is made again once with the other key, and the key that worked is kept. An answer about the
    model is raised as it is. The first real run (2026-11-08) showed that agent_reference is the key: the service called agent deprecated."""

    REFUSED = {"code": "unknown_parameter", "message": "Unknown parameter: 'agent_reference'."}
    NOTE = "Foundry response: the key agent_reference was refused (unknown_parameter: Unknown parameter: 'agent_reference'.); agent is used from now on"
    UNRELATED = {"code": "invalid_request_error", "message": "Missing required parameter: 'model'."}
    # The two answers of the first real run, as the app read them. The first message goes on with the id of the request, which is left out here.
    MODEL_ERROR = {"code": "model_error", "message": "Function tools with reasoning_effort are not supported for gpt-6.1-sol in /v1/chat/completions. "
                                                      "To use function tools, use /v1/responses or set reasoning_effort to 'none'."}
    MODEL_ERROR_WORDS = ("model_error: Function tools with reasoning_effort are not supported for gpt-6.1-sol in /v1/chat/completions. "
                         "To use function tools, use /v1/responses or set reasoning_effort to 'none'.")
    DEPRECATED = {"code": "invalid_payload", "message": "The 'agent' property is deprecated. Use 'agent_reference' instead"}
    # An HTTP 400 about the model, its reasoning effort or its function tools: the other key cannot mend it, so it is raised as it is.
    ABOUT_THE_MODEL = (
        MODEL_ERROR, {"code": "model_error"}, {"code": "MODEL_ERROR", "message": "The model failed."}, {"code": "invalid_request_error", "message": "Unsupported model: it does not support function tools."},
        {"message": "Unsupported model: it does not support function tools."}, {"message": "The reasoning effort 'high' is not supported."},
        {"code": "invalid_request_error", "message": "reasoning_effort: unknown value"}, {"message": "Function tool calls need the Responses route."},
    )
    # A 400 that is not about the model, and the reason that the note gives for it: the words of the service, or that there are none.
    BODIES = (
        ({"error": {"code": "unknown_parameter", "message": "Unknown parameter: 'agent_reference'."}}, "unknown_parameter: Unknown parameter: 'agent_reference'."),
        ({"error": {"message": "Unrecognized request argument supplied: agent_reference"}}, "Unrecognized request argument supplied: agent_reference"),
        ({"error": {"code": "invalid_request_error", "message": "Unsupported parameter: agent"}}, "invalid_request_error: Unsupported parameter: agent"),
        ({"error": {"message": "Missing required parameter: 'agent'."}}, "Missing required parameter: 'agent'."),
        ({"error": {"code": "unknown_parameter"}}, "unknown_parameter"),
        ({"error": {"code": "invalid_request_error", "message": "Missing required parameter: 'model'."}}, "invalid_request_error: Missing required parameter: 'model'."),
        ({"error": {"code": "invalid_request_error", "message": "The 'model' parameter is required"}}, "invalid_request_error: The 'model' parameter is required"),
        ({"error": {"code": "invalid_request_error", "message": "The model deployment 'gpt-6.1-sol' does not exist."}},
         "invalid_request_error: The model deployment 'gpt-6.1-sol' does not exist."),
        ({"error": {"message": "Agent 'meternaut-investigator' version '3' was not found."}}, "Agent 'meternaut-investigator' version '3' was not found."),
        ({"error": {"code": "BadRequest", "message": "Invalid model deployment."}}, "BadRequest: Invalid model deployment."),
        ({"error": {"code": "model_not_found", "message": "The model 'x' was not found."}}, "model_not_found: The model 'x' was not found."),
        ({"error": {"message": "Invalid value for 'instructions'."}}, "Invalid value for 'instructions'."),
        ({"error": {"code": "content_filter", "message": "The prompt was filtered."}}, "content_filter: The prompt was filtered."),
        ({"error": {"code": "x"}}, "x"), ({"error": {}}, "no reason given"), ({"error": "text"}, "no reason given"), ({"message": "top level words"}, "no reason given"),
        ([], "no reason given"), (b"<html>unknown parameter 'agent_reference'</html>", "no reason given"), (b"", "no reason given"), ("plain text", "no reason given"),
    )

    @staticmethod
    def keys(rig):
        """The key of the agent reference in each body that was posted to /responses, in order."""
        return [next(key for key in ("agent_reference", "agent") if key in call["body"]) for call in rig.service.calls if call["route"] == "POST responses"]

    def test_a_service_that_wants_agent_gets_the_other_key_once_and_the_same_body_otherwise(self):
        rig = Rig()
        rig.service.accepts = "agent"
        result = rig.run(reply([message("ok")], 40, 6))
        self.assertEqual((result.text, result.responses, result.input_tokens, result.output_tokens), ("ok", 1, 40, 6))
        self.assertEqual(self.keys(rig), ["agent_reference", "agent"])
        reference = {"type": "agent_reference", "name": NAME, "version": "3"}
        self.assertEqual(rig.service.responses, [{"agent_reference": reference, "conversation": "conv_0001abc", "input": []},
                                                 {"agent": reference, "conversation": "conv_0001abc", "input": []}])
        self.assertEqual(rig.service.routes(), ["POST conversations", "POST responses", "POST responses", "DELETE conversation"])
        self.assertEqual(rig.foundry.notes, [self.NOTE])

    def test_the_key_that_worked_is_used_for_every_later_call_of_the_client_and_a_function_output_goes_once(self):
        rig = Rig()
        rig.service.accepts = "agent"
        rig.run(reply([call("t", {}, "c1")]), reply([message("one")]), handler=Handler('{"a":1}'))
        rig.service.replies = [reply([message("two")])]
        self.assertEqual(rig.foundry.run(AGENT, "Again.").text, "two")
        rig.service.replies = [reply([message("three")])]
        rig.foundry.run("meternaut-skeptic:1", "And the other agent.", None, max_calls=0)
        self.assertEqual(self.keys(rig), ["agent_reference", "agent", "agent", "agent", "agent"])
        self.assertEqual([item for body in rig.service.responses for item in body["input"]], [output_of("c1", '{"a":1}')])
        self.assertEqual(rig.foundry.notes, [self.NOTE], "said once")

    def test_a_service_that_wants_agent_reference_gets_one_call_and_no_second_try_after_that(self):
        rig = Rig()
        rig.service.accepts = "agent_reference"
        self.assertEqual(rig.run(reply([message("ok")])).text, "ok")
        self.assertEqual((self.keys(rig), rig.foundry.notes), (["agent_reference"], []))
        rig.service.accepts = "agent"
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.run(AGENT, "Again.")
        self.assertEqual(self.keys(rig), ["agent_reference", "agent_reference"], "the key was settled by the first answer")
        self.assertEqual(str(raised.exception), "Foundry response failed: HTTP 400; unknown_parameter: Unknown parameter: 'agent_reference'.")

    def test_any_400_on_the_first_call_that_is_not_about_the_model_is_made_again_once_with_the_other_key_whatever_else_it_says(self):
        for body, reason in self.BODIES:
            with self.subTest(body=body):
                rig = Rig()
                rig.service.accepts = "agent"
                rig.service.failures["POST responses"] = [(400, body), PASS]
                result = rig.run(reply([message("ok")], 40, 6))
                self.assertEqual((result.text, result.responses, (result.input_tokens, result.output_tokens)), ("ok", 1, (40, 6)))
                self.assertEqual(self.keys(rig), ["agent_reference", "agent"])
                self.assertEqual(rig.service.routes(), ["POST conversations", "POST responses", "POST responses", "DELETE conversation"])
                self.assertEqual(rig.foundry.notes, [f"Foundry response: the key agent_reference was refused ({reason}); agent is used from now on"])

    def test_a_400_about_the_model_is_raised_as_it_is_and_is_not_made_again_with_the_other_key(self):
        # The service would take the other key here: it is not asked. The first real run was refused by the model, and the call with the other key only hid that answer.
        for body in self.ABOUT_THE_MODEL:
            for status in (400, 422):
                with self.subTest(body=body, status=status):
                    rig = Rig()
                    rig.service.accepts = "agent"
                    rig.service.failures["POST responses"] = [(status, {"error": body}), PASS]
                    with self.assertRaises(FoundryError) as raised:
                        rig.run(reply([message("never")]))
                    self.assertEqual((self.keys(rig), raised.exception.status, rig.foundry.notes), (["agent_reference"], status, []))
                    self.assertEqual(rig.service.routes(), ["POST conversations", "POST responses", "DELETE conversation"])
                    self.assertEqual((raised.exception.partial.responses, rig.service.conversations), (0, {}))
                    rig.service.accepts = "agent_reference"
                    rig.service.replies = [reply([message("ok")])]
                    self.assertEqual(rig.foundry.run(AGENT, "Again.").text, "ok")
                    self.assertEqual(self.keys(rig), ["agent_reference", "agent_reference"], "the first answer settled the key")

    def test_the_first_answer_of_the_real_run_is_raised_with_its_code_and_its_words_and_nothing_is_made_again(self):
        rig = Rig()
        rig.service.failures["POST responses"] = (400, {"error": self.MODEL_ERROR})
        with self.assertRaises(FoundryError) as raised:
            rig.run()
        self.assertEqual(str(raised.exception), f"Foundry response failed: HTTP 400; {self.MODEL_ERROR_WORDS}")
        self.assertEqual((raised.exception.status, raised.exception.code, raised.exception.words), (400, "model_error", self.MODEL_ERROR_WORDS))
        self.assertEqual((self.keys(rig), rig.foundry.notes), (["agent_reference"], []))

    def test_when_the_service_calls_the_other_key_deprecated_the_first_key_was_right_and_the_first_answer_is_raised(self):
        # The second answer of the real run says nothing of why the first call failed: the first answer is the real one, and agent_reference stays.
        for body, reason in self.BODIES:
            with self.subTest(body=body):
                rig = Rig()
                rig.service.failures["POST responses"] = [(400, body), (400, {"error": self.DEPRECATED})]
                with self.assertRaises(FoundryError) as raised:
                    rig.run()
                self.assertEqual((self.keys(rig), raised.exception.status), (["agent_reference", "agent"], 400), "the other key was tried once")
                self.assertNotIn("deprecated", str(raised.exception))
                self.assertEqual(rig.foundry.notes, ["Foundry response: the service says that the key agent is deprecated, so agent_reference stays, "
                                                     f"and the first answer is the real one ({reason})"])
                self.assertEqual((raised.exception.partial.responses, rig.service.conversations), (0, {}))

    def test_the_first_answer_that_is_raised_after_a_deprecated_key_keeps_its_words_and_agent_reference_is_used_by_the_next_run(self):
        first = {"code": "invalid_request_error", "message": "The request is invalid."}
        rig = Rig()
        rig.service.failures["POST responses"] = [(400, {"error": first}), (400, {"error": self.DEPRECATED})]
        with self.assertRaises(FoundryError) as raised:
            rig.run()
        self.assertEqual(str(raised.exception), "Foundry response failed: HTTP 400; invalid_request_error: The request is invalid.")
        self.assertEqual((raised.exception.code, raised.exception.words), ("invalid_request_error", "invalid_request_error: The request is invalid."))
        rig.service.failures.clear()
        rig.service.accepts = "agent_reference"
        rig.service.replies = [reply([message("ok")])]
        self.assertEqual(rig.foundry.run(AGENT, "Again.").text, "ok")
        self.assertEqual(self.keys(rig), ["agent_reference", "agent", "agent_reference"], "the key that the service wants is the first one, and the next run starts with it")
        self.assertEqual(len(rig.foundry.notes), 1, "said once")

    def test_a_second_answer_that_is_not_about_a_deprecated_key_is_raised_as_before(self):
        for words in ("Unknown parameter: 'agent'.", "The 'agent' property is not allowed.", "deprecated", "The model is deprecated."):
            with self.subTest(words=words):
                rig = Rig()
                rig.service.failures["POST responses"] = [(400, {"error": self.REFUSED}), (400, {"error": {"message": words}})]
                with self.assertRaises(FoundryError) as raised:
                    rig.run()
                self.assertEqual(str(raised.exception), f"Foundry response failed: HTTP 400; {words}")
                self.assertEqual(rig.foundry.notes, ["Foundry response: the key agent_reference was refused (unknown_parameter: Unknown parameter: 'agent_reference'.), and agent failed too"])

    def test_the_other_key_is_sent_with_the_same_body_when_the_400_is_about_something_else(self):
        rig = Rig()
        rig.service.accepts = "agent"
        rig.service.refusal = self.UNRELATED
        self.assertEqual(rig.run(reply([message("ok")])).text, "ok")
        reference = {"type": "agent_reference", "name": NAME, "version": "3"}
        self.assertEqual(rig.service.responses, [{"agent_reference": reference, "conversation": "conv_0001abc", "input": []},
                                                 {"agent": reference, "conversation": "conv_0001abc", "input": []}])
        self.assertEqual(rig.foundry.notes, ["Foundry response: the key agent_reference was refused (invalid_request_error: Missing required parameter: 'model'.); "
                                             "agent is used from now on"])

    def test_the_key_that_worked_after_any_400_is_used_for_every_later_call_and_run_of_the_client(self):
        rig = Rig()
        rig.service.accepts = "agent"
        rig.service.refusal = self.UNRELATED
        rig.run(reply([call("t", {}, "c1")]), reply([message("one")]), handler=Handler('{"a":1}'))
        rig.service.replies = [reply([message("two")])]
        self.assertEqual(rig.foundry.run(AGENT, "Again.").text, "two")
        rig.service.replies = [reply([message("three")])]
        rig.foundry.run("meternaut-skeptic:1", "And the other agent.", None, max_calls=0)
        self.assertEqual(self.keys(rig), ["agent_reference", "agent", "agent", "agent", "agent"])
        self.assertEqual([item for body in rig.service.responses for item in body["input"]], [output_of("c1", '{"a":1}')], "the output went once")
        self.assertEqual(len(rig.foundry.notes), 1, "said once")

    def test_a_400_on_a_later_call_is_never_made_again_whatever_it_says(self):
        # The second response of a run carries the output of a function: it is not made again, so the output goes once.
        for what, answer in (("the words of a refused key", {"error": self.REFUSED}), ("other words", {"error": self.UNRELATED}), ("no words", {})):
            with self.subTest(what):
                rig = Rig()
                rig.service.replies = [reply([call("t", {}, "c1")]), (400, answer)]
                with self.assertRaises(FoundryError) as raised:
                    rig.foundry.run(AGENT, "Go.", Handler('{"a":1}'))
                self.assertEqual(self.keys(rig), ["agent_reference", "agent_reference"])
                self.assertEqual([item for body in rig.service.responses for item in body["input"]], [output_of("c1", '{"a":1}')])
                self.assertEqual((raised.exception.status, rig.foundry.notes), (400, []))
                self.assertTrue(str(raised.exception).startswith("Foundry function output failed: HTTP 400"), str(raised.exception))

    def test_no_other_status_is_made_again_whatever_the_words_say(self):
        for what, body in (("the words of a refused key", {"error": self.REFUSED}), ("other words", {"error": self.UNRELATED}), ("no words", {})):
            for status in (401, 403, 404, 409, 410, 500, 502, 504):
                with self.subTest(what=what, status=status):
                    rig = Rig()
                    rig.service.failures["POST responses"] = (status, body)
                    with self.assertRaises(FoundryError) as raised:
                        rig.run()
                    self.assertEqual((self.keys(rig), raised.exception.status, rig.foundry.notes), (["agent_reference"], status, []))
            for failure in ((503, {}, body), (429, {"retry-after": "1"}, body)):
                with self.subTest(what=what, status=failure[0]):
                    rig = Rig()
                    rig.service.failures["POST responses"] = failure
                    with self.assertRaises(FoundryError):
                        rig.run()
                    self.assertEqual(self.keys(rig), ["agent_reference"] * (fo.RATE_RETRIES + 1), "the client waits and asks again with the same key, which is not the other key")
        for failure in (urllib.error.URLError("down"), TimeoutError("slow")):
            with self.subTest(failure=failure):
                rig = Rig()
                rig.service.failures["POST responses"] = failure
                with self.assertRaises(FoundryError):
                    rig.run()
                self.assertEqual(self.keys(rig), ["agent_reference"])

    def test_a_422_on_the_first_call_is_made_again_once_with_the_other_key_and_on_a_later_call_never(self):
        rig = Rig()
        rig.service.accepts = "agent"
        rig.service.failures["POST responses"] = [(422, {"error": {"code": "validation_error", "message": "Extra inputs are not permitted"}}), PASS]
        self.assertEqual(rig.run(reply([message("ok")])).text, "ok")
        self.assertEqual(self.keys(rig), ["agent_reference", "agent"])
        self.assertEqual(rig.foundry.notes, ["Foundry response: the key agent_reference was refused (validation_error: Extra inputs are not permitted); agent is used from now on"])
        rig = Rig()
        rig.service.replies = [reply([call("t", {}, "c1")]), (422, {})]
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.run(AGENT, "Go.", Handler('{"a":1}'))
        self.assertEqual((self.keys(rig), raised.exception.status, rig.foundry.notes), (["agent_reference", "agent_reference"], 422, []))

    def test_a_second_failure_is_raised_like_any_failure_and_says_in_a_note_what_the_first_one_was(self):
        second = {"code": "unknown_parameter", "message": "Unknown parameter: 'agent'."}
        rig = Rig()
        rig.service.failures["POST responses"] = [(400, {"error": self.REFUSED}), (400, {"error": second})]
        with self.assertRaises(FoundryError) as raised:
            rig.run()
        self.assertEqual(self.keys(rig), ["agent_reference", "agent"])
        self.assertEqual(str(raised.exception), "Foundry response failed: HTTP 400; unknown_parameter: Unknown parameter: 'agent'.")
        self.assertEqual((raised.exception.status, raised.exception.partial.responses), (400, 0))
        self.assertEqual(rig.foundry.notes, ["Foundry response: the key agent_reference was refused (unknown_parameter: Unknown parameter: 'agent_reference'.), and agent failed too"])
        self.assertEqual((rig.service.routes()[-1], rig.service.conversations), ("DELETE conversation", {}))
        rig.service.calls.clear()
        rig.service.responses.clear()
        with self.assertRaises(FoundryError):
            rig.foundry.run(AGENT, "Again.")
        self.assertEqual(self.keys(rig), ["agent_reference"], "nothing worked, so the key is the first one, and there is no second try for the second run")

    def test_the_words_in_the_note_are_the_words_of_the_refusal_redacted_and_cut_and_nothing_of_the_request(self):
        words = f"The token {JWT} and {TOKEN} and {TOKEN[:20]}\x00{TOKEN[20:]} are not valid\n\x1b[31m red " + "m" * 400
        refusal = (400, {"error": {"code": f"Invalid-{JWT}", "message": words}})
        prefix = "Foundry response: the key agent_reference was refused ("
        for works, suffix in ((True, "); agent is used from now on"), (False, "), and agent failed too")):
            with self.subTest(second_try_works=works):
                rig = Rig()
                rig.service.failures["POST responses"] = [refusal, PASS if works else refusal]
                if works:
                    rig.run(reply([message("ok")]))
                else:
                    with self.assertRaises(FoundryError) as raised:
                        rig.run()
                    for secret in (JWT, TOKEN, TOKEN[:20], TOKEN[20:]):
                        self.assertNotIn(secret, str(raised.exception))
                        self.assertNotIn(secret, raised.exception.words)
                (note,) = rig.foundry.notes
                self.assertTrue(note.startswith(prefix) and note.endswith(suffix), note)
                reason = note[len(prefix):-len(suffix)]
                self.assertEqual(len(reason), 200, "cut like the words of any error")
                self.assertIn("[redacted]", reason)
                self.assertTrue(all(ch.isprintable() for ch in note), "no control character")
                for secret in (JWT, TOKEN, TOKEN[:20], TOKEN[20:], "eyJ", "SECRET"):
                    self.assertNotIn(secret, note)

    def test_a_note_and_its_log_line_are_redacted_at_the_end_whatever_made_the_text(self):
        rig = Rig()
        rig.foundry.ensure_agent(spec())  # the token is asked for and registered
        with LogCapture() as logs:
            rig.foundry._note(f"something {TOKEN} and {JWT} happened")
        (note,) = rig.foundry.notes
        self.assertEqual(note, "something [redacted] and [redacted] happened")
        self.assertEqual([m for m in logs.messages() if "something" in m], [note])

    def test_a_second_try_that_fails_for_another_reason_is_that_failure(self):
        rig = Rig()
        rig.service.failures["POST responses"] = [(400, {"error": self.REFUSED}), (404, {"error": {"code": "not_found", "message": "Agent not found"}})]
        with self.assertRaises(FoundryError) as raised:
            rig.run()
        self.assertEqual(str(raised.exception), "Foundry response failed: HTTP 404; DNS of the endpoint host: private; not_found: Agent not found")

    def test_a_second_400_is_raised_and_the_note_says_what_the_first_one_was_even_when_the_words_are_about_something_else(self):
        second = {"code": "model_not_found", "message": "The model deployment 'gpt-6.1-sol' does not exist."}
        rig = Rig()
        rig.service.failures["POST responses"] = [(400, {"error": self.UNRELATED}), (400, {"error": second})]
        with self.assertRaises(FoundryError) as raised:
            rig.run()
        self.assertEqual(self.keys(rig), ["agent_reference", "agent"], "once more and no more")
        self.assertEqual(str(raised.exception), "Foundry response failed: HTTP 400; model_not_found: The model deployment 'gpt-6.1-sol' does not exist.")
        self.assertEqual((raised.exception.status, raised.exception.partial.responses), (400, 0))
        self.assertEqual(rig.foundry.notes, ["Foundry response: the key agent_reference was refused (invalid_request_error: Missing required parameter: 'model'.), and agent failed too"])
        self.assertEqual((rig.service.routes()[-1], rig.service.conversations), ("DELETE conversation", {}))
        rig = Rig()
        rig.service.failures["POST responses"] = (400, {})
        with self.assertRaises(FoundryError) as raised:
            rig.run()
        self.assertEqual(str(raised.exception), "Foundry response failed: HTTP 400")
        self.assertEqual(rig.foundry.notes, ["Foundry response: the key agent_reference was refused (no reason given), and agent failed too"])

    def test_only_the_first_response_that_the_service_answers_is_ever_made_again(self):
        # The first call that was answered, whether it worked or failed (its repeat included), settles the key: the first response of a later run is not made again.
        rig = Rig()
        rig.service.failures["POST responses"] = [(400, {"error": {"code": "x", "message": "one"}}), (400, {"error": {"code": "y", "message": "two"}}),
                                                  (400, {"error": {"code": "z", "message": "three"}})]
        with self.assertRaises(FoundryError):
            rig.run()
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.run(AGENT, "Again.")
        self.assertEqual(self.keys(rig), ["agent_reference", "agent", "agent_reference"], "nothing worked, so the first key again, and no second try")
        self.assertEqual(str(raised.exception), "Foundry response failed: HTTP 400; z: three")
        self.assertEqual(len(rig.foundry.notes), 1, "only the first run said anything")
        # Another client has a first call of its own.
        other = Rig()
        other.service.accepts = "agent"
        other.run(reply([message("ok")]))
        self.assertEqual(self.keys(other), ["agent_reference", "agent"])

    def test_a_call_with_a_function_output_is_never_made_again_even_when_the_first_call_is_still_open(self):
        # Not reachable through run(): a function output follows an answer. It is the second guard of the rule, so it is tried on its own.
        for refusal in ({"code": "unknown_parameter", "message": "Unknown parameter: '{key}'."}, self.UNRELATED, {}):
            with self.subTest(refusal=refusal):
                rig = Rig()
                rig.service.accepts = "agent"
                rig.service.refusal = refusal
                rig.service.replies = [reply([message("must not be asked for")])]
                conversation = rig.foundry._conversation("Go.")
                with self.assertRaises(FoundryError) as raised:
                    rig.foundry._respond({"type": "agent_reference", "name": NAME}, conversation, [output_of("c1", '{"a":1}')], "function output")
                self.assertEqual((raised.exception.status, self.keys(rig), rig.foundry.notes), (400, ["agent_reference"], []))

    def test_a_first_call_that_the_service_never_answered_is_not_the_first_that_it_answered(self):
        rig = Rig()
        rig.service.accepts = "agent"
        rig.service.failures["POST responses"] = [urllib.error.URLError("down"), PASS]
        with self.assertRaises(FoundryError):
            rig.run(reply([message("never")]))
        rig.service.replies = [reply([message("ok")])]
        self.assertEqual(rig.foundry.run(AGENT, "Again.", None, max_calls=0).text, "ok")
        self.assertEqual(self.keys(rig), ["agent_reference", "agent_reference", "agent"])

    def test_the_second_try_has_the_same_deadline(self):
        rig = Rig()
        rig.service.accepts = "agent"
        rig.service.advance = 10
        with self.assertRaises(FoundryError) as raised:
            rig.run(reply([message("late")]), max_seconds=15)
        self.assertEqual(str(raised.exception), "Foundry response failed: the time allowed was used up")
        self.assertEqual(self.keys(rig), ["agent_reference"])
        self.assertEqual(rig.foundry.notes, ["Foundry response: the key agent_reference was refused (unknown_parameter: Unknown parameter: 'agent_reference'.), and agent failed too"])

    def test_the_default_key_is_the_one_of_the_rest_reference(self):
        rig = Rig()
        rig.run(reply([message("ok")]))
        self.assertEqual((self.keys(rig), fo.AGENT_KEYS), (["agent_reference"], ("agent_reference", "agent")))


class KeyWords(unittest.TestCase):
    """The words of an HTTP 400 decide only whether it is about the model, its reasoning effort or its function tools: the first call is made again with the other key
    unless it is, whatever else its message says, and no later call ever is."""

    WORDS = (
        # words that name a key or a parameter
        "unknown_parameter: Unknown parameter: 'agent_reference'.", "Unknown parameter: 'agent'.", "Unrecognized request argument supplied: agent_reference",
        "Unsupported parameter: agent", "Invalid parameter: agent_reference", "The parameter 'agent' is not supported.", "parameter agent_reference is unknown",
        "The field 'agent' is not recognized", "invalid_parameter", "unsupported_parameter: nope", "Unrecognized field 'agent_reference'", "Property 'agent' is not allowed",
        "Missing required parameter: 'agent'.", "agent_reference: Field required", "AGENT_REFERENCE is missing", "The 'agent_reference' property is invalid",
        "Invalid value for parameter 'conversation'", "invalid_request_error: Unknown parameter: 'agent'.", 'Unknown argument "agent"', "unknown `agent` key",
        # words that are about something else, or about nothing
        "The model deployment 'gpt-6.1-sol' does not exist.", "Agent 'meternaut-investigator' was not found.", "Agent version '3' of 'meternaut-investigator' does not exist.",
        "Invalid model deployment.", "Invalid value for 'instructions'.",
        "invalid_request_error: The request is invalid.", "invalid_request_error: The 'model' parameter is required", "Conversation 'conv_1' not found.",
        "The input is too long.", "", "Rate limit exceeded", "Invalid API version", "Unknown model", "Required parameter 'input' is missing.",
        "Missing required parameter. The model is invalid.", "invalid_request_error", "BadRequest: The request body could not be parsed",
        "The agent is not available in this region", "Agent: meternaut-investigator not found", "agents are not enabled", "reference_agent is fine",
        "The value of agent_reference_version was not found", "Value x_agent_reference was not found",
    )
    # Words about the model, its reasoning effort or its function tools: the other key cannot mend them.
    ABOUT_THE_MODEL = (
        "Unsupported model: this model does not support function tools.", "Function tools with reasoning_effort are not supported for gpt-6.1-sol in /v1/chat/completions.",
        "The reasoning effort 'high' is not supported by this model.", "reasoning_effort: unknown value", "Function tool calls need the Responses route.",
        "REASONING EFFORT is not allowed here", "Unsupported model: it does not support function tools.",
    )

    def test_a_400_on_the_first_call_is_made_again_with_the_other_key_whatever_its_message_says_unless_it_is_about_the_model(self):
        for words in self.WORDS:
            with self.subTest(words=words):
                rig = Rig()
                rig.service.accepts = "agent"
                rig.service.failures["POST responses"] = [(400, {"error": {"message": words}}), PASS]
                self.assertEqual(rig.run(reply([message("ok")])).text, "ok")
                self.assertEqual(TheKeyOfTheAgent.keys(rig), ["agent_reference", "agent"])

    def test_a_400_on_the_first_call_whose_message_is_about_the_model_is_raised_and_never_made_again(self):
        for words in self.ABOUT_THE_MODEL:
            with self.subTest(words=words):
                rig = Rig()
                rig.service.accepts = "agent"
                rig.service.failures["POST responses"] = [(400, {"error": {"message": words}}), PASS]
                with self.assertRaises(FoundryError) as raised:
                    rig.run(reply([message("never")]))
                self.assertEqual((TheKeyOfTheAgent.keys(rig), raised.exception.status, rig.foundry.notes), (["agent_reference"], 400, []))

    def test_the_same_words_on_a_call_that_is_not_the_first_are_never_made_again(self):
        for words in self.WORDS + self.ABOUT_THE_MODEL:
            with self.subTest(words=words):
                rig = Rig()
                rig.service.replies = [reply([call("t", {}, "c1")]), (400, {"error": {"message": words}})]
                with self.assertRaises(FoundryError) as raised:
                    rig.foundry.run(AGENT, "Go.", Handler())
                self.assertEqual((TheKeyOfTheAgent.keys(rig), raised.exception.status, rig.foundry.notes), (["agent_reference", "agent_reference"], 400, []))


class Race(unittest.TestCase):
    """Another run made the agent between the read and the creation: the creation answers 409, and that is no failure."""

    NOT_THERE = (404, {"error": {"code": "not_found", "message": "Agent not found"}})

    def raced(self, other_spec, spec_of_this_run):
        """A run whose read says that the agent is not there while the agent is there: the other run was first."""
        rig = Rig()
        rig.foundry.ensure_agent(other_spec)
        rig.service.failures["GET agent"] = [self.NOT_THERE, PASS]
        rig.service.calls.clear()
        return rig, rig.foundry.ensure_agent(spec_of_this_run)

    def test_a_409_on_the_creation_reads_the_agent_and_finds_the_same_definition(self):
        with LogCapture() as logs:
            rig, result = self.raced(spec(), spec())
        self.assertEqual(result, f"{NAME}:1")
        self.assertEqual(rig.service.routes(), ["GET agent", "POST agents", "GET agent"])
        self.assertEqual(len(rig.service.agents[NAME]), 1, "no version was made")
        self.assertEqual((rig.lookup.calls, rig.foundry.notes), ([], []))
        self.assertIn(f"Foundry agent {NAME}: made by another run", logs.messages())
        rig.service.calls.clear()
        self.assertEqual(rig.foundry.ensure_agent(spec()), f"{NAME}:1")
        self.assertEqual(rig.service.routes(), ["GET agent"], "and after it the agent costs one read")

    def test_a_409_on_the_creation_reads_the_agent_and_makes_a_new_version_when_the_definition_differs(self):
        rig, result = self.raced(spec(model="gpt-6-luna"), spec())
        self.assertEqual(result, f"{NAME}:2")
        self.assertEqual(rig.service.routes(), ["GET agent", "POST agents", "GET agent", "POST versions"])
        made = rig.service.agents[NAME][1]
        self.assertEqual((made["definition"]["model"], rig.service.calls[3]["path"]), ("gpt-6.1-sol", f"/agents/{NAME}/versions"))
        self.assertNotIn("name", rig.service.calls[3]["body"])
        rig.service.calls.clear()
        self.assertEqual(rig.foundry.ensure_agent(spec()), f"{NAME}:2")
        self.assertEqual(rig.service.routes(), ["GET agent"])

    def test_the_creation_that_the_other_run_made_is_read_like_any_agent(self):
        for what, document in (("no version", {"name": NAME}), ("another name", {"versions": {"latest": {"name": "other", "version": "1"}}})):
            with self.subTest(what):
                rig = Rig()
                rig.foundry.ensure_agent(spec())
                rig.service.failures["GET agent"] = [self.NOT_THERE, (200, document)]
                with self.assertRaises(FoundryError) as raised:
                    rig.foundry.ensure_agent(spec())
                self.assertIn("Foundry read agent failed", str(raised.exception))

    def test_an_agent_that_is_still_not_there_after_a_409_is_the_failure_of_the_creation(self):
        rig = Rig()
        rig.service.failures["POST agents"] = (409, {"error": {"code": "conflict", "message": "The agent exists"}})
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        self.assertEqual(str(raised.exception), "Foundry create agent failed: HTTP 409; conflict: The agent exists")
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(rig.service.routes(), ["GET agent", "POST agents", "GET agent"])
        self.assertEqual(rig.lookup.calls, [], "a 409 carries no DNS fact")

    def test_a_read_after_a_409_that_fails_is_the_failure_of_that_read(self):
        rig = Rig()
        rig.service.failures["POST agents"] = (409, {})
        rig.service.failures["GET agent"] = [self.NOT_THERE, (403, {"error": {"code": "PermissionDenied", "message": "no right"}})]
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        self.assertEqual(str(raised.exception), "Foundry read agent failed: HTTP 403; DNS of the endpoint host: private; PermissionDenied: no right")

    def test_no_other_failure_of_the_creation_reads_the_agent_again(self):
        for status in (400, 401, 403, 404, 408, 422, 500):
            with self.subTest(status=status):
                rig = Rig()
                rig.service.failures["POST agents"] = (status, {})
                with self.assertRaises(FoundryError) as raised:
                    rig.foundry.ensure_agent(spec())
                self.assertEqual((raised.exception.status, rig.service.routes()), (status, ["GET agent", "POST agents"]))

    def test_a_409_on_a_new_version_is_not_a_race_of_this_kind_and_is_a_failure(self):
        rig = Rig()
        rig.foundry.ensure_agent(spec())
        rig.service.failures["POST versions"] = (409, {"error": {"code": "conflict", "message": "busy"}})
        rig.service.calls.clear()
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec(model="gpt-6-luna"))
        self.assertEqual((raised.exception.status, rig.service.routes()), (409, ["GET agent", "POST versions"]))


class DnsFact(unittest.TestCase):
    """When a call fails with no answer, a 403 or a 404, the error says where the host name of the endpoint leads."""

    def error_of(self, rig, failure, route="POST agents"):
        rig.service.failures[route] = failure
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        return str(raised.exception)

    def test_a_connection_error_a_403_and_a_404_carry_the_fact(self):
        body = {"error": {"code": "X", "message": "Y"}}
        for lookup, word in ((Lookup("10.1.2.3"), "private"), (Lookup("20.30.40.50"), "public"), (Lookup(error=socket.gaierror(-2, "Name or service not known")), "unresolved")):
            for failure, start in ((urllib.error.URLError("down"), "Foundry create agent failed: no answer (the connection failed or timed out)"),
                                   (TimeoutError("slow"), "Foundry create agent failed: no answer (the connection failed or timed out)"),
                                   ((403, body), "Foundry create agent failed: HTTP 403"), ((404, body), "Foundry create agent failed: HTTP 404")):
                with self.subTest(word=word, failure=failure):
                    text = self.error_of(Rig(lookup=lookup), failure)
                    self.assertTrue(text.startswith(start), text)
                    self.assertIn(f"; DNS of the endpoint host: {word}", text)
                    self.assertFalse(re.search(r"\d+\.\d+\.\d+\.\d+", text), "no address is named")
                    if isinstance(failure, tuple):
                        self.assertTrue(text.endswith("; X: Y"), "the fact comes before the words of the service, so that a cut of the text keeps it")

    def test_the_fact_comes_with_a_403_on_the_read_of_an_agent_too_and_a_404_there_is_not_a_failure(self):
        rig = Rig(lookup=Lookup("192.168.4.5"))
        rig.service.failures["GET agent"] = (403, {"error": {"code": "PermissionDenied", "message": "no right"}})
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        self.assertEqual(str(raised.exception), "Foundry read agent failed: HTTP 403; DNS of the endpoint host: private; PermissionDenied: no right")
        rig = Rig()
        rig.foundry.ensure_agent(spec())
        self.assertEqual(rig.lookup.calls, [], "an agent that is not there is the normal answer to a read")

    def test_no_other_failure_carries_it_and_the_host_is_not_looked_up(self):
        for failure in ((400, {}), (401, {}), (409, {}), (410, {}), (422, {}), (500, {}), (502, {}), (503, {}), (504, {}), (429, {"retry-after": "3600"}, {}), (200, b"not json")):
            with self.subTest(failure=failure[0]):
                rig = Rig()
                text = self.error_of(rig, failure)
                self.assertNotIn("DNS", text)
                self.assertEqual(rig.lookup.calls, [])

    def test_the_host_is_looked_up_once_for_all_the_failures_of_a_client(self):
        rig = Rig(lookup=Lookup("8.8.4.4"))
        for _ in range(3):
            self.assertIn("DNS of the endpoint host: public", self.error_of(rig, (403, {})))
        self.assertEqual(rig.lookup.calls, [(HOST, 443, {"type": socket.SOCK_STREAM})], "only the host name, never the address of the endpoint")

    def test_a_lookup_that_fails_in_any_way_is_the_word_unresolved(self):
        for error in (socket.gaierror(-3, "temporary"), OSError("x"), TimeoutError("slow"), RuntimeError("boom"), ValueError("v"), KeyError("k"), UnicodeError("u")):
            with self.subTest(error=error):
                self.assertIn("; DNS of the endpoint host: unresolved", self.error_of(Rig(lookup=Lookup(error=error)), (403, {})))

    def test_a_deadline_is_not_a_connection_error(self):
        rig = Rig()
        rig.client.deadline = 900.0
        with self.assertRaises(FoundryError) as raised:
            rig.foundry.ensure_agent(spec())
        self.assertEqual(str(raised.exception), "Foundry read agent failed: the time allowed was used up")
        self.assertEqual(rig.lookup.calls, [])


class HostKind(unittest.TestCase):
    def kind(self, *addresses, error=None):
        return fo.host_kind("h.example", Lookup(*addresses, error=error))

    def test_every_address_in_the_three_ranges_of_rfc_1918_is_private(self):
        for address in ("10.0.0.0", "10.1.2.3", "10.255.255.255", "172.16.0.0", "172.20.5.5", "172.31.255.255", "192.168.0.0", "192.168.1.1", "192.168.255.255"):
            self.assertEqual(self.kind(address), "private", address)

    def test_an_address_just_outside_the_ranges_or_in_any_other_range_is_public(self):
        for address in ("9.255.255.255", "11.0.0.0", "172.15.255.255", "172.32.0.0", "192.167.255.255", "192.169.0.0", "8.8.8.8", "20.30.40.50", "100.64.0.1", "127.0.0.1",
                        "169.254.1.1", "0.0.0.0", "255.255.255.255"):
            self.assertEqual(self.kind(address), "public", address)

    def test_addresses_of_the_second_kind_are_read_too(self):
        for address, word in (("2603:1030:800::1", "public"), ("::1", "public"), ("fd00::1", "public"), ("fe80::1%eth0", "public"), ("::ffff:10.1.2.3", "private"),
                              ("::ffff:192.168.0.9", "private"), ("::ffff:8.8.8.8", "public"), ("::ffff:172.32.0.1", "public")):
            self.assertEqual(self.kind(address), word, address)

    def test_it_takes_every_address_to_be_private(self):
        for addresses, word in ((("10.0.0.1", "8.8.8.8"), "public"), (("8.8.8.8", "10.0.0.1"), "public"), (("10.0.0.1", "192.168.1.1", "172.16.0.9"), "private"),
                                (("10.0.0.1", "::1"), "public"), (("10.0.0.1", "::ffff:10.0.0.2"), "private")):
            self.assertEqual(self.kind(*addresses), word, addresses)

    def test_a_name_that_does_not_resolve_or_an_answer_that_cannot_be_read_is_unresolved(self):
        self.assertEqual(self.kind(), "unresolved", "an empty answer")
        for error in (socket.gaierror(-2, "x"), OSError("x"), TimeoutError(), RuntimeError("boom"), ValueError("v"), KeyError("k"), AssertionError("a")):
            self.assertEqual(self.kind(error=error), "unresolved", repr(error))
        for answer in (["not-an-address"], [()], [None], [("a",)], [(1, 2, 3, 4, ())], [(1, 2, 3, 4, (None, 443))], [(1, 2, 3, 4, ("10.0.0.1",))] + [5], "abc", 5, None):
            with self.subTest(answer=answer):
                self.assertEqual(fo.host_kind("h.example", lambda host, port, **options: answer), "unresolved")

    def test_it_gives_one_of_three_words_and_never_an_address(self):
        for addresses in (("10.0.0.1",), ("8.8.8.8",), ("2603:1030::1",), ()):
            self.assertIn(self.kind(*addresses), {"private", "public", "unresolved"})

    def test_the_resolver_gets_the_host_the_https_port_and_a_stream_type(self):
        lookup = Lookup("10.0.0.1")
        fo.host_kind("name.example", lookup)
        self.assertEqual(lookup.calls, [("name.example", 443, {"type": socket.SOCK_STREAM})])


class TheListOfCalls(unittest.TestCase):
    """http.allowed_calls with the endpoint of a project: what the client may call, and the calls that it may not."""

    LIST = http.allowed_calls(ENDPOINT)

    def check(self, method, url):
        Client(self.LIST, Redactor()).check(method, url)

    def test_the_calls_of_the_client_are_allowed(self):
        for method, path in (("GET", f"/agents/{NAME}?api-version=v1"), ("POST", "/agents?api-version=v1"), ("POST", f"/agents/{NAME}/versions?api-version=v1"),
                             ("POST", "/openai/v1/conversations"), ("POST", "/openai/v1/responses"),
                             ("DELETE", "/openai/v1/conversations/conv_0001abc"),
                             ("GET", f"/agents/{'a' * 63}"), ("DELETE", "/openai/v1/conversations/conv_" + "A_b-9" * 20)):
            self.check(method, f"{ENDPOINT}{path}")

    def test_no_chat_completion_to_the_foundry_resource_or_project_is_allowed_a_model_is_called_through_the_ai_gateway_only(self):
        # Every model call of Meternaut goes through the AI Gateway (AGENTS.md rule 15 (c)): neither the project's route nor the resource's route of a chat completion is on the list.
        for url in (f"{ENDPOINT}/openai/v1/chat/completions", f"https://{HOST}/openai/v1/chat/completions", f"{ENDPOINT}/openai/chat/completions",
                    f"https://{HOST}/openai/deployments/gpt-6-luna/chat/completions", f"{ENDPOINT}/chat/completions"):
            for method in ("POST", "GET"):
                with self.subTest(method=method, url=url):
                    with self.assertRaises(http.Refused):
                        self.check(method, url)
        for _, pattern in self.LIST:
            self.assertNotIn("chat", pattern.pattern, "no call of the Foundry list is a chat completion")
        self.assertFalse(hasattr(http, "resource_of") or hasattr(http, "CHAT_PATH"), "the route of the project and of the resource, and their fallback, are gone")

    def test_without_the_endpoint_the_app_makes_no_call_to_foundry_and_the_other_calls_are_the_same(self):
        plain = http.allowed_calls()
        self.assertEqual(self.LIST[:len(plain)], plain)
        self.assertEqual(len(self.LIST) - len(plain), 6)
        client = Client(plain, Redactor())
        for method, path in (("GET", f"/agents/{NAME}"), ("POST", "/agents"), ("POST", "/openai/v1/responses"), ("POST", "/openai/v1/chat/completions"),
                             ("DELETE", "/openai/v1/conversations/conv_1")):
            with self.assertRaises(http.Refused):
                client.check(method, f"{ENDPOINT}{path}")
        with self.assertRaises(http.Refused):
            client.check("POST", f"https://{HOST}/openai/v1/chat/completions")
        self.assertEqual(http.allowed_calls(None), http.allowed_calls())

    def test_the_added_calls_are_exactly_these_and_all_on_the_host_of_the_project(self):
        added = [(method, pattern.pattern) for method, pattern in self.LIST[len(self.LIST) - 6:]]
        base = re.escape(ENDPOINT)
        self.assertEqual(added, [("GET", base + f"/agents/{http.FOUNDRY_AGENT_NAME}"), ("POST", base + "/agents"), ("POST", base + f"/agents/{http.FOUNDRY_AGENT_NAME}/versions"),
                                 ("POST", base + "/openai/v1/conversations"), ("POST", base + "/openai/v1/responses"),
                                 ("DELETE", base + f"/openai/v1/conversations/{http.FOUNDRY_CONVERSATION_ID}")])
        self.assertEqual({m for m, _ in added}, {"GET", "POST", "DELETE"})
        self.assertEqual([m for m, p in added if "chat" in p], [], "no chat completion is on the list of the Foundry project")

    def test_another_host_another_account_another_project_and_another_scheme_are_refused(self):
        paths = (f"/agents/{NAME}", "/agents", "/openai/v1/responses", "/openai/v1/conversations", "/openai/v1/conversations/conv_1")
        methods = {f"/agents/{NAME}": "GET", "/agents": "POST", "/openai/v1/responses": "POST", "/openai/v1/conversations": "POST", "/openai/v1/conversations/conv_1": "DELETE"}
        for other in (f"https://other-account.services.ai.azure.com{PROJECT}", f"https://{HOST}/api/projects/proj-example2", f"https://{HOST}/api/projects/proj-exampl",
                      f"https://{HOST}/api/projects/PROJ-EXAMPLE", f"https://{HOST}/api/projects/_project", f"https://{HOST.upper()}{PROJECT}", f"http://{HOST}{PROJECT}",
                      f"https://{HOST}.evil.example{PROJECT}", f"https://evil.example/{HOST}{PROJECT}", f"https://acct-example.openai.azure.com{PROJECT}",
                      f"https://acct-example.cognitiveservices.azure.com{PROJECT}", f"https://{HOST}:8443{PROJECT}", f"https://user@{HOST}{PROJECT}", f"https://{HOST}/api{PROJECT}",
                      f"https://{HOST.replace('.', '-')}{PROJECT}",
                      f"https://{HOST}/other{PROJECT}", f"https://{HOST}/api/projects/proj-example/../other"):
            for path in paths:
                with self.subTest(other=other, path=path):
                    with self.assertRaises(http.Refused):
                        self.check(methods[path], other + path)

    def test_a_put_a_patch_and_any_other_method_are_refused_everywhere(self):
        for method in ("PUT", "PATCH", "HEAD", "OPTIONS", "TRACE", "get", "post", "delete"):
            for path in (f"/agents/{NAME}", "/agents", f"/agents/{NAME}/versions", "/openai/v1/conversations", "/openai/v1/conversations/conv_1", "/openai/v1/responses"):
                with self.subTest(method=method, path=path):
                    with self.assertRaises(http.Refused):
                        self.check(method, ENDPOINT + path)

    def test_what_is_not_the_call_of_the_client_is_refused_on_the_endpoint_of_the_project(self):
        refused = (
            ("DELETE", f"/agents/{NAME}"), ("DELETE", f"/agents/{NAME}/versions/1"), ("DELETE", "/agents"), ("GET", "/agents"), ("GET", f"/agents/{NAME}/versions"),
            ("GET", f"/agents/{NAME}/versions/1"), ("POST", f"/agents/{NAME}"), ("POST", f"/agents/{NAME}/import"), ("POST", f"/agents/{NAME}/versions:import"),
            ("POST", "/agents/"), ("GET", "/agents/"), ("POST", f"/agents/{NAME}/versions/"), ("POST", f"/agents/{NAME}/versions/1"), ("GET", "/openai/v1/conversations"),
            ("GET", "/openai/v1/conversations/conv_1"), ("POST", "/openai/v1/conversations/conv_1"), ("POST", "/openai/v1/conversations/conv_1/items"),
            ("DELETE", "/openai/v1/conversations"), ("DELETE", "/openai/v1/conversations/"), ("DELETE", "/openai/v1/conversations/conv_1/items/x"),
            ("DELETE", "/openai/v1/conversations/other"), ("DELETE", "/openai/v1/conversations/conv_"), ("DELETE", "/openai/v1/conversations/conv_a/b"),
            ("DELETE", "/openai/v1/conversations/conv_../x"), ("DELETE", "/openai/v1/conversations/conv_" + "a" * 101), ("DELETE", "/openai/v1/responses/resp_1"),
            ("GET", "/openai/v1/responses"), ("GET", "/openai/v1/responses/resp_1"), ("POST", "/openai/v1/responses/resp_1/cancel"), ("POST", "/openai/v1/responses/"),
            ("POST", "/openai/v1/files"), ("GET", "/openai/v1/files"), ("POST", "/evaluations"), ("GET", "/connections"), ("GET", "/deployments"), ("POST", "/openai/v1/vector_stores"),
            ("POST", "/openai/responses"), ("GET", "/"), ("POST", ""), ("GET", f"/agents/{'a' * 64}"), ("GET", "/agents/a b"), ("GET", "/agents/-a"), ("GET", "/agents/a-"),
            ("GET", "/agents/a%2Fb"), ("GET", "/agents/a/b"), ("GET", "/agents/../agents/x"), ("POST", "/agents/x/versions/../.."), ("GET", f"/agents/{NAME}/endpoint/protocols/openai/responses"),
            ("POST", f"/agents/{NAME}/endpoint/protocols/openai/responses"), ("POST", f"/agents/{NAME}/endpoint/protocols/openai/conversations"),
        )
        for method, path in refused:
            with self.subTest(method=method, path=path):
                with self.assertRaises(http.Refused):
                    self.check(method, ENDPOINT + path)

    def test_a_query_string_does_not_change_what_a_call_is(self):
        self.check("POST", ENDPOINT + "/openai/v1/responses?x=1&api-version=v1")
        with self.assertRaises(http.Refused):
            self.check("PUT", ENDPOINT + "/openai/v1/responses?x=1")

    def test_an_endpoint_that_is_not_the_endpoint_of_a_project_is_refused_when_the_list_is_made(self):
        for endpoint in ("", "https://", f"https://{HOST}", ENDPOINT + "/", ENDPOINT + "/agents", f"http://{HOST}{PROJECT}", "https://evil.example/api/projects/p",
                         f"https://{HOST.upper()}{PROJECT}", f"https://{HOST}{PROJECT}?x=1", f"https://{HOST}/api/projects/.", f"https://{HOST}/api/projects/..",
                         f"https://{HOST}/api/projects/.p", f"https://{HOST}/api/projects/..p"):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    http.allowed_calls(endpoint)
        http.allowed_calls("https://a1.services.ai.azure.com/api/projects/_project")
        http.allowed_calls("https://a1.services.ai.azure.com/api/projects/proj.v2")

    def test_the_dot_of_a_project_name_is_a_dot_and_not_any_character_in_the_list_of_calls(self):
        dotted = f"https://{HOST}/api/projects/proj.v2"
        client = Client(http.allowed_calls(dotted), Redactor())
        for method, path in (("GET", f"/agents/{NAME}"), ("POST", "/agents"), ("POST", f"/agents/{NAME}/versions"), ("POST", "/openai/v1/conversations"),
                             ("POST", "/openai/v1/responses"), ("DELETE", "/openai/v1/conversations/conv_1")):
            client.check(method, dotted + path)
            for other in ("projXv2", "proj-v2", "proj_v2", "proj.v3", "proj.v", "proj..v2", "proj.v2.x", "proj", "proj.v2/.."):
                with self.subTest(method=method, path=path, other=other):
                    with self.assertRaises(http.Refused):
                        client.check(method, f"https://{HOST}/api/projects/{other}{path}")

    def test_a_client_that_makes_the_calls_of_the_client_makes_no_call_that_the_list_refuses(self):
        # Every call of a whole run and of the making of an agent was allowed by the list: a refusal would have been a FoundryError, and there was none.
        rig = Rig()
        rig.foundry.ensure_agent(spec())
        rig.foundry.ensure_agent(spec(model="gpt-6-luna"))
        rig.foundry.ensure_agent(spec(model="gpt-6-luna"))
        rig.run(reply([call("t", {}, "c1")]), reply([message("x")]), handler=Handler())
        self.assertEqual(sorted(set(rig.service.routes())), sorted({"GET agent", "POST agents", "POST versions", "POST conversations", "POST responses", "DELETE conversation"}))


if __name__ == "__main__":
    unittest.main()
