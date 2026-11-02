import email.message
import io
import json
import ssl
import unittest
import urllib.error
import urllib.request
import urllib.response
from unittest import mock

from harness import client as client_module
from harness.client import (ClientError, Completion, GuardedClient, HubClient, ScriptedClient, StopRun, _build_opener,
                            _NoRedirect, _PinnedHTTPSConnection, _PinnedHTTPSHandler)

ENV = {"C14_HUB_CHAT_URL": "https://hub.example/openai/chat/completions", "C14_HUB_MODEL": "reasoner", "C14_HUB_KEY": "k"}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_network(fake):
    """Stand in for the network: `fake(request, timeout)` answers every request that a client opens."""
    return mock.patch.object(urllib.request.OpenerDirector, "open",
                             lambda self, request, data=None, timeout=None: fake(request, timeout))


class RedirectingHandler(urllib.request.BaseHandler):
    """A hub that answers every HTTPS request with a redirect to plain HTTP on another host."""
    handler_order = 100

    def https_open(self, req):
        headers = email.message.Message()
        headers["Location"] = "http://elsewhere.example/collect"
        response = urllib.response.addinfourl(io.BytesIO(b""), headers, req.full_url, 302)
        response.msg = "Found"
        return response


def reply(text="hello", prompt=11, completion=7):
    body = {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}
    return FakeResponse(json.dumps(body).encode("utf-8"))


def http_error(code, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://hub.example", code, "x", headers, io.BytesIO(b"busy"))


class HubClientTests(unittest.TestCase):
    def test_the_route_and_the_credentials_are_required(self):
        with self.assertRaises(ClientError) as raised:
            HubClient({})
        self.assertIn("C14_HUB_CHAT_URL", str(raised.exception))
        with self.assertRaises(ClientError):
            HubClient({"C14_HUB_CHAT_URL": "https://hub.example/x", "C14_HUB_MODEL": "m"})

    def test_only_https_is_accepted(self):
        with self.assertRaises(ClientError):
            HubClient({**ENV, "C14_HUB_CHAT_URL": "http://hub.example/x"})

    def test_a_call_sends_the_key_the_model_and_both_messages(self):
        seen = {}

        def fake_urlopen(request, timeout):
            seen["headers"] = {k.lower(): v for k, v in request.header_items()}
            seen["body"] = json.loads(request.data)
            return reply("answer", 5, 2)

        with fake_network(fake_urlopen):
            completion = HubClient({**ENV, "C14_HUB_MAX_TOKENS": "900"}).complete("system text", "user text")
        self.assertEqual(completion, Completion("answer", 5, 2))
        self.assertEqual(seen["headers"]["api-key"], "k")
        self.assertNotIn("authorization", seen["headers"])
        self.assertEqual(seen["body"]["model"], "reasoner")
        self.assertEqual([m["role"] for m in seen["body"]["messages"]], ["system", "user"])
        self.assertEqual(seen["body"]["max_completion_tokens"], 900)

    def test_a_bearer_token_is_sent_in_addition_to_the_key(self):
        seen = {}

        def fake_urlopen(request, timeout):
            seen["headers"] = {k.lower(): v for k, v in request.header_items()}
            return reply()

        env = {**ENV, "C14_HUB_BEARER": "token"}
        with fake_network(fake_urlopen):
            HubClient(env).complete("s", "u")
        self.assertEqual(seen["headers"]["authorization"], "Bearer token")
        self.assertEqual(seen["headers"]["api-key"], "k")

    def test_a_bearer_token_alone_is_refused_because_the_hub_requires_the_key(self):
        env = {k: v for k, v in ENV.items() if k != "C14_HUB_KEY"} | {"C14_HUB_BEARER": "token"}
        with self.assertRaises(ClientError) as raised:
            HubClient(env)
        self.assertIn("C14_HUB_KEY", str(raised.exception))

    def test_a_connect_address_must_be_an_ip_address(self):
        with self.assertRaises(ClientError):
            HubClient({**ENV, "C14_HUB_CONNECT_ADDRESS": "hub.example"})

    def test_an_address_adds_the_pinned_handler_and_never_a_proxy(self):
        proxy = {"HTTPS_PROXY": "http://proxy.example:3128", "https_proxy": "http://proxy.example:3128"}
        with mock.patch.dict("os.environ", proxy):
            pinned = _build_opener("10.52.0.4").handlers
            plain = _build_opener().handlers
        self.assertEqual([h._connect_address for h in pinned if isinstance(h, _PinnedHTTPSHandler)], ["10.52.0.4"])
        self.assertFalse(any(isinstance(h, urllib.request.ProxyHandler) for h in pinned))
        self.assertTrue(any(isinstance(h, urllib.request.ProxyHandler) for h in plain), "the control: a plain opener uses the proxy")
        self.assertFalse(any(isinstance(h, _PinnedHTTPSHandler) for h in plain))

    def test_no_opener_follows_a_redirect(self):
        for address in ("", "10.52.0.4"):
            handlers = _build_opener(address).handlers
            self.assertTrue(any(isinstance(h, _NoRedirect) for h in handlers))
            self.assertFalse(any(type(h) is urllib.request.HTTPRedirectHandler for h in handlers))

    def test_a_redirect_is_an_error_and_the_key_goes_nowhere_else(self):
        real = client_module._build_opener
        for address in ("", "10.52.0.4"):
            env = {**ENV, "C14_HUB_CONNECT_ADDRESS": address} if address else ENV
            with mock.patch.object(client_module, "_build_opener", lambda a="", real=real: real(a, RedirectingHandler())):
                with self.assertRaises(ClientError) as raised:
                    HubClient(env, attempts=1).complete("s", "u")
            self.assertIn("302", str(raised.exception))
            self.assertNotIn("elsewhere.example", str(raised.exception) + repr(raised.exception.__cause__))

    def test_a_connect_address_is_used_for_the_timeout_of_the_opener_call(self):
        seen = {}

        def fake(request, timeout):
            seen["timeout"] = timeout
            return reply("pinned")

        with fake_network(fake):
            completion = HubClient({**ENV, "C14_HUB_CONNECT_ADDRESS": "10.52.0.4"}, timeout=7.0).complete("s", "u")
        self.assertEqual((completion.text, seen["timeout"]), ("pinned", 7.0))

    def test_a_pinned_connection_verifies_the_certificate_against_the_name(self):
        connection = _PinnedHTTPSConnection("hub.example", 443, connect_address="10.52.0.4")
        self.assertTrue(connection._context.check_hostname)
        self.assertEqual(connection._context.verify_mode, ssl.CERT_REQUIRED)

    def test_a_pinned_connection_goes_to_the_address_and_keeps_the_name_for_tls(self):
        seen = {}

        class FakeContext:
            def wrap_socket(self, sock, server_hostname=None):
                seen["server_hostname"] = server_hostname
                return sock

        def fake_create_connection(address, timeout=None, source_address=None):
            seen["address"] = address
            return object()

        connection = _PinnedHTTPSConnection("hub.example", 443, connect_address="10.52.0.4", context=FakeContext())
        with mock.patch("socket.create_connection", fake_create_connection):
            connection.connect()
        self.assertEqual(seen["address"], ("10.52.0.4", 443))
        self.assertEqual(seen["server_hostname"], "hub.example")

    def test_a_busy_hub_is_retried_with_its_retry_after(self):
        outcomes = [http_error(429, "3"), reply("late")]
        sleeps = []

        def fake_urlopen(request, timeout):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        client = HubClient(ENV, sleep=sleeps.append)
        with fake_network(fake_urlopen):
            self.assertEqual(client.complete("s", "u").text, "late")
        self.assertEqual(sleeps, [3.0])
        self.assertEqual(client.requests, 2)

    def test_a_refusal_is_an_error_and_never_shows_the_key(self):
        def fake_urlopen(request, timeout):
            raise http_error(401)

        with fake_network(fake_urlopen):
            with self.assertRaises(ClientError) as raised:
                HubClient({**ENV, "C14_HUB_KEY": "SECRET-KEY-123"}).complete("s", "u")
        self.assertIn("401", str(raised.exception))
        self.assertNotIn("SECRET-KEY-123", str(raised.exception))

    def test_a_reply_that_is_not_a_chat_completion_is_an_error(self):
        with fake_network(lambda request, timeout: FakeResponse(b'{"nope": 1}')):
            with self.assertRaises(ClientError):
                HubClient(ENV).complete("s", "u")


class GuardTests(unittest.TestCase):
    def test_the_call_limit_stops_the_run(self):
        client = GuardedClient(ScriptedClient(lambda s, u: "x"), max_calls=2)
        client.complete("s", "u")
        client.complete("s", "u")
        with self.assertRaises(StopRun):
            client.complete("s", "u")

    def test_the_cap_stops_the_run_once_the_cost_reaches_it(self):
        client = GuardedClient(ScriptedClient(lambda s, u: Completion("x", 1_000_000, 0)), max_calls=10, prices=(1.0, 1.0),
                               cap_eur=1.0, max_completion_tokens=100)
        client.complete("s", "u")
        self.assertAlmostEqual(client.cost_eur, 1.0)
        with self.assertRaises(StopRun):
            client.complete("s", "u")

    def test_a_call_that_could_pass_the_cap_is_refused_before_it_is_made(self):
        inner = ScriptedClient(lambda s, u: "x")
        client = GuardedClient(inner, max_calls=10, prices=(1.0, 1.0), cap_eur=0.5, max_completion_tokens=600_000)
        with self.assertRaises(StopRun) as raised:
            client.complete("s", "u")
        self.assertIn("could pass the spending cap", str(raised.exception))
        self.assertEqual(inner.calls, 0)

    def test_the_prompt_is_part_of_the_worst_case(self):
        inner = ScriptedClient(lambda s, u: "x")
        client = GuardedClient(inner, max_calls=10, prices=(1.0, 1.0), cap_eur=0.4, max_completion_tokens=1)
        with self.assertRaises(StopRun):
            client.complete("s", "u" * 1_000_000)
        self.assertEqual(inner.calls, 0)

    def test_a_cap_needs_prices_and_a_reply_limit(self):
        inner = ScriptedClient(lambda s, u: "x")
        with self.assertRaises(ValueError):
            GuardedClient(inner, max_calls=2, cap_eur=1.0)
        with self.assertRaises(ValueError):
            GuardedClient(inner, max_calls=2, cap_eur=1.0, prices=(1.0, 1.0))
        with self.assertRaises(ValueError):
            GuardedClient(inner, max_calls=2, cap_eur=1.0, max_completion_tokens=10)

    def test_calls_already_used_count_against_the_limit_and_the_cost(self):
        client = GuardedClient(ScriptedClient(lambda s, u: Completion("x", 10, 0)), max_calls=2, prices=(1.0, 1.0), used=(1, 100, 10))
        client.complete("s", "u")
        self.assertEqual((client.calls, client.prompt_tokens, client.completion_tokens), (2, 110, 10))
        with self.assertRaises(StopRun):
            client.complete("s", "u")

    def test_the_hub_is_told_the_reply_limit_of_the_stage(self):
        seen = {}

        def fake_urlopen(request, timeout):
            seen["body"] = json.loads(request.data)
            return reply()

        with fake_network(fake_urlopen):
            HubClient({**ENV, "C14_HUB_MAX_TOKENS": "900"}, max_tokens=50).complete("s", "u")
        self.assertEqual(seen["body"]["max_completion_tokens"], 50)

    def test_without_prices_the_cost_is_unknown(self):
        client = GuardedClient(ScriptedClient(lambda s, u: "x"), max_calls=2)
        client.complete("s", "u")
        self.assertIsNone(client.cost_eur)


if __name__ == "__main__":
    unittest.main()
